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
    _dhcp_server_statistics_delta,
    _dhcp_server_statistics_observation,
    _dhcp_server_statistics_point,
    _post_failure_simulation_diagnostic,
    _representative_phone_evidence,
    _trunk_vlan_traversal_evidence,
    _voice_dhcp_statistics_target,
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

def statistics_plan(*, control=True):
    actions = [
        SimpleNamespace(
            action_type=ConfigurationActionType.CONFIGURE_DHCP_POOL,
            device_name="Router4",
            segment_id="large-voice",
        ),
        SimpleNamespace(
            action_type=ConfigurationActionType.CONFIGURE_SUBINTERFACE,
            device_name="Router4",
            segment_id="large-voice",
            parent_interface="FastEthernet0/0",
            vlan_id=20,
        ),
    ]
    if control:
        actions.extend([
            SimpleNamespace(
                action_type=ConfigurationActionType.CONFIGURE_DHCP_POOL,
                device_name="Router4",
                segment_id="large-data",
            ),
            SimpleNamespace(
                action_type=ConfigurationActionType.CONFIGURE_SUBINTERFACE,
                device_name="Router4",
                segment_id="large-data",
                parent_interface="FastEthernet0/0",
                vlan_id=10,
            ),
        ])
    return SimpleNamespace(actions=actions)

phones = SimpleNamespace(phone_assignments=[SimpleNamespace(
    voice_segment_id="large-voice",
)])
statistics_target = _voice_dhcp_statistics_target(statistics_plan(), phones)
verdict["dhcp_statistics_target"] = statistics_target
# A server with only the voice pool offers nothing to discriminate against, so
# the interface argument could never be observed to scope. No target at all.
verdict["dhcp_statistics_target_without_control"] = _voice_dhcp_statistics_target(
    statistics_plan(control=False), phones,
)

class StatisticsIos:
    """Answers per interface, which is what a scoped build would do."""

    def __init__(self, outputs):
        self.outputs = outputs
        self.calls = []

    def execute(self, device_name, query_id, *, interface=""):
        self.calls.append((device_name, query_id.value, interface))
        return IosCommandResult(
            device_name=device_name,
            query_id=query_id,
            executed=True,
            output=self.outputs[interface],
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

def statistics_output(discover, offer, request, ack, nak):
    return f"""Router4#show ip dhcp server statistics FastEthernet0/0.20
Message               Received
DHCPDISCOVER          {{discover}}
DHCPREQUEST           {{request}}
Message               Sent
DHCPOFFER             {{offer}}
DHCPACK               {{ack}}
DHCPNAK               {{nak}}
Router4#"""

def statistics_pair(voice, control):
    return {{
        "FastEthernet0/0.20": statistics_output(*voice),
        "FastEthernet0/0.10": statistics_output(*control),
    }}

QUIET = (0, 0, 0, 0, 0)

def statistics_delta(baseline_pair, post_pair, *, voice_binding_count=0):
    baseline_ios = StatisticsIos(baseline_pair)
    post_ios = StatisticsIos(post_pair)
    delta = _dhcp_server_statistics_delta(
        _dhcp_server_statistics_point(baseline_ios, statistics_target),
        _dhcp_server_statistics_point(post_ios, statistics_target),
        voice_binding_count=voice_binding_count,
    )
    return delta, baseline_ios.calls + post_ios.calls

# The voice subinterface saw an offered exchange the data subinterface did not:
# the interface argument demonstrably scoped this read.
scoped_delta, scoped_calls = statistics_delta(
    statistics_pair(QUIET, QUIET),
    statistics_pair((21, 21, 0, 0, 0), (23, 23, 23, 23, 0)),
)
verdict["dhcp_statistics_calls"] = scoped_calls
verdict["dhcp_statistics_delta"] = scoped_delta

# Both subinterfaces reported the same non-zero counters: this build answered
# for the server, not for the interface, and the 23 data clients that acquire
# in the same window are inside every number.
verdict["dhcp_statistics_scope_unproven"] = statistics_delta(
    statistics_pair(QUIET, QUIET),
    statistics_pair((44, 44, 23, 23, 0), (44, 44, 23, 23, 0)),
)[0]

# Identical AND zero is different: a global table could not have read zero
# across this window, so an observed absence of DISCOVER survives.
verdict["dhcp_statistics_quiet_window"] = statistics_delta(
    statistics_pair(QUIET, QUIET), statistics_pair(QUIET, QUIET),
)[0]

# A cumulative counter that went down is not negative DHCP traffic.
verdict["dhcp_statistics_counter_reset"] = statistics_delta(
    statistics_pair((5, 5, 5, 5, 0), (5, 5, 5, 5, 0)),
    statistics_pair((1, 1, 1, 1, 0), (7, 7, 7, 7, 0)),
)[0]

# A control scope that cannot be read leaves scoping unproven, even when the
# voice scope read perfectly.
verdict["dhcp_statistics_control_unreadable"] = statistics_delta(
    statistics_pair(QUIET, QUIET),
    {{
        "FastEthernet0/0.20": statistics_output(21, 21, 0, 0, 0),
        "FastEthernet0/0.10": "Router4#\\n% Invalid input detected at '^' marker.\\nRouter4#",
    }},
)[0]

unsupported_ios = StatisticsIos(statistics_pair(QUIET, QUIET))
unsupported_ios.outputs["FastEthernet0/0.20"] = (
    "Router4#show ip dhcp server statistics FastEthernet0/0.20\\n"
    "% Invalid input detected at '^' marker.\\nRouter4#"
)
verdict["dhcp_statistics_unsupported"] = (
    _dhcp_server_statistics_observation(unsupported_ios, statistics_target)
)
truncated_ios = StatisticsIos(statistics_pair((1, 1, 1, 1, 0), QUIET))
truncated_execute = truncated_ios.execute
def execute_truncated(device_name, query_id, *, interface=""):
    return replace(
        truncated_execute(device_name, query_id, interface=interface),
        output_complete=False,
        truncated_by_pager=True,
    )
truncated_ios.execute = execute_truncated
verdict["dhcp_statistics_truncated"] = (
    _dhcp_server_statistics_observation(truncated_ios, statistics_target)
)
wrong_statistics_ios = StatisticsIos(statistics_pair((1, 1, 1, 1, 0), QUIET))
wrong_statistics_execute = wrong_statistics_ios.execute
def execute_wrong_statistics_identity(device_name, query_id, *, interface=""):
    return replace(
        wrong_statistics_execute(device_name, query_id, interface=interface),
        observed_device_name="AnotherRouter",
        device_identity_provenance=DeviceIdentityProvenance.MISMATCHED.value,
    )
wrong_statistics_ios.execute = execute_wrong_statistics_identity
verdict["dhcp_statistics_wrong_identity"] = (
    _dhcp_server_statistics_observation(wrong_statistics_ios, statistics_target)
)

PHONE_NAME = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PHONE-02"
PC_NAME = "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PC-01"
PHONE_ID = "endpoint/large-branch/campus/floor-1/zone-a/ip_phone/002"
PC_ID = "endpoint/large-branch/campus/floor-1/zone-a/user_pc/001"

def sim_topology():
    phone = SimpleNamespace(id=PHONE_ID, name=PHONE_NAME, model="7960")
    pc = SimpleNamespace(id=PC_ID, name=PC_NAME, model="PC-PT")
    sw5 = SimpleNamespace(id="sw-acc-zone-a-02", name="Switch5", model="2960")
    sw4 = SimpleNamespace(id="sw-acc-zone-a-01", name="Switch4", model="2960")
    return SimpleNamespace(
        topology=SimpleNamespace(
            devices=[phone, pc, sw5, sw4],
            links=[
                SimpleNamespace(
                    device_a_id=sw5.id, port_a="FastEthernet0/2",
                    device_b_id=PHONE_ID, port_b="Switch",
                ),
                SimpleNamespace(
                    device_a_id=sw4.id, port_a="FastEthernet0/1",
                    device_b_id=PC_ID, port_b="FastEthernet0",
                ),
            ],
        ),
    )

def sim_voice(**overrides):
    row = {{
        "phone_id": PHONE_ID, "extension": "3002", "status": "failed",
        "evidence_method": "fresh_privileged_show_ephone", "fresh_evidence": True,
        "endpoint_interface": "Vlan20", "endpoint_interface_present": True,
        "endpoint_address_channel": True, "endpoint_dhcp_enabled": True,
        "endpoint_ipv4": "",
    }}
    row.update(overrides)
    return {{"staged": True, "error": "voice failed", "result": {{"registrations": [row]}}}}

class SimBridge:
    """Scripted PT bridge. Records every script the diagnostic dispatches."""

    def __init__(self, *, mode=False, step=None, trace=None, restore_mode=None):
        self.mode = mode
        self.scripts = []
        self._step = step
        self._trace = trace
        self._restore_mode = restore_mode

    def __call__(self, script, timeout):
        self.scripts.append(script)
        if "getFrameInstanceAt" in script:
            if self._trace is None:
                return None
            frames = self._trace.get(
                PHONE_NAME if PHONE_NAME in script else PC_NAME, [],
            )
            return json.dumps({{
                "total": 4096, "simulation_mode": True, "frames": frames,
            }})
        if "setSimulationMode" in script:
            before = self.mode
            want = "setSimulationMode(true)" in script
            self.mode = want if self._restore_mode is None else self._restore_mode
            return json.dumps({{
                "before": before, "after": self.mode, "frames": 3, "sim_time": 1.0,
            }})
        if "resetSimulation" in script or "__s.forward();" in script:
            if self._step is None:
                return None
            return json.dumps(self._step)
        return json.dumps({{
            "mode": self.mode, "frames": 7, "sim_time": 2.5, "current_index": 1,
        }})

def sim_frame(**overrides):
    base = {{
        "index": 0, "device": PHONE_NAME, "previous_device": None,
        "in_port": None, "out_port": "Switch", "source": "0.0.0.0",
        "destination": "255.255.255.255", "traffic_type_raw": 77,
        "sim_time": 3.25, "transit_time": 0.0, "sent": True,
        "decisions": [
            {{"layer": 3, "inbound": False, "description": "The device sets it."}},
            {{"layer": 2, "inbound": False, "description": "The device sends it."}},
        ],
    }}
    base.update(overrides)
    return base

STEP_OK = {{
    "simulation_mode": True, "frames_before": 0, "frames_after": 11,
    "sim_time": 4.0, "current_index": 10,
}}

# -- 17: a run that started in Realtime is returned to Realtime -------------
realtime_bridge = SimBridge(
    mode=False, step=STEP_OK,
    trace={{PHONE_NAME: [sim_frame()], PC_NAME: []}},
)
verdict["sim_realtime"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=realtime_bridge), sim_topology(), sim_voice(),
)
verdict["sim_realtime_final_mode"] = realtime_bridge.mode
verdict["sim_realtime_scripts"] = len(realtime_bridge.scripts)
verdict["sim_realtime_mutators"] = sorted({{
    token for token in (
        "setDhcpClientFlag", "renew", "release", "setIpAddress", "setDefaultGateway",
        "setSubnetMask", "add(", "remove(", "delete", "savePkt", "setConfig",
    )
    for script in realtime_bridge.scripts if token in script
}})

# -- 18: a run that ALREADY was in Simulation is left in Simulation ---------
sim_bridge = SimBridge(
    mode=True, step=STEP_OK, trace={{PHONE_NAME: [], PC_NAME: []}},
)
verdict["sim_preexisting"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=sim_bridge), sim_topology(), sim_voice(),
)
verdict["sim_preexisting_final_mode"] = sim_bridge.mode
verdict["sim_preexisting_set_calls"] = sum(
    1 for script in sim_bridge.scripts if "setSimulationMode" in script
)

# -- 19: the trace times out; restoration still happens --------------------
trace_timeout = SimBridge(mode=False, step=STEP_OK, trace=None)
verdict["sim_trace_timeout"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=trace_timeout), sim_topology(), sim_voice(),
)
verdict["sim_trace_timeout_final_mode"] = trace_timeout.mode

# -- 20: the step fails; restoration still happens -------------------------
step_failure = SimBridge(mode=False, step=None, trace=None)
verdict["sim_step_failure"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=step_failure), sim_topology(), sim_voice(),
)
verdict["sim_step_failure_final_mode"] = step_failure.mode

# -- 21: restoration itself fails and is recorded on its own key -----------
stuck = SimBridge(
    mode=False, step=STEP_OK,
    trace={{PHONE_NAME: [sim_frame()], PC_NAME: []}},
    restore_mode=True,
)
verdict["sim_restore_failed"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=stuck), sim_topology(), sim_voice(),
)

# -- 16: prerequisites are re-checked from THIS run ------------------------
verdict["sim_prereq_addressed"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=SimBridge(mode=False)),
    sim_topology(), sim_voice(endpoint_ipv4="172.16.20.5"),
)
verdict["sim_prereq_dhcp_off"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=SimBridge(mode=False)),
    sim_topology(), sim_voice(endpoint_dhcp_enabled=False),
)
verdict["sim_prereq_unreadable"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=SimBridge(mode=False)),
    sim_topology(), sim_voice(endpoint_address_channel=False),
)
verdict["sim_prereq_missing_row"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=SimBridge(mode=False)),
    sim_topology(), sim_voice(phone_id="endpoint/somebody/else"),
)
verdict["sim_prereq_ok"] = _representative_phone_evidence(
    sim_topology(), sim_voice(), PHONE_NAME,
)

# -- the original state itself must be attributable before anything moves --
blind = SimBridge(mode=False)
blind_scripts = []
def blind_bridge(script, timeout):
    blind_scripts.append(script)
    return None
verdict["sim_blind"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=blind_bridge), sim_topology(), sim_voice(),
)
verdict["sim_blind_mutated"] = any(
    "setSimulationMode" in script for script in blind_scripts
)

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
live._dhcp_server_statistics_point = lambda *args, **kwargs: {{
    "sentinel": "post statistics retained",
}}
live._dhcp_server_statistics_delta = lambda *args, **kwargs: {{
    "sentinel": "statistics delta retained",
}}
live._post_failure_simulation_diagnostic = lambda *args, **kwargs: {{
    "sentinel": "post failure simulation retained",
}}
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
        dhcp_statistics_target={{"device_name": "Router4"}},
        dhcp_statistics_baseline={{"usable": True}},
        verified_serial_topology=SimpleNamespace(),
        verified_serial_manifest=SimpleNamespace(),
    )
except CanonicalLiveFailure as exc:
    voice_failure_evidence = exc.stage_evidence or {{}}
    verdict["bindings_before_voice_failure"] = voice_failure_evidence.get(
        "dhcp_server_bindings"
    )
    verdict["statistics_before_voice_failure"] = voice_failure_evidence.get(
        "dhcp_voice_exchange"
    )
    verdict["simulation_before_voice_failure"] = voice_failure_evidence.get(
        "post_failure_simulation"
    )
else:
    verdict["bindings_before_voice_failure"] = None
    verdict["statistics_before_voice_failure"] = None
    verdict["simulation_before_voice_failure"] = None

# ---- VOICE_REALTIME_CONTINUITY -------------------------------------------
# Simulation mode changes execution semantics, so a 180s convergence window
# that ran while it was active is not the same experiment. Both boundaries of
# the authoritative window have to be observed Realtime before its 0/21 result
# may be read as a voice contradiction at all.
REALTIME_STATE = {{"mode": False, "frames": 0, "sim_time": 0.0, "current_index": -1}}
SIMULATING_STATE = {{"mode": True, "frames": 5, "sim_time": 2.0, "current_index": 1}}

class ContinuityBridge:
    def __init__(self, *states):
        self.states = list(states)
        self.scripts = []

    def __call__(self, script, timeout):
        self.scripts.append(script)
        state = self.states.pop(0) if self.states else None
        return None if state is None else json.dumps(state)

voice_invocations = []
live._stage_voice = lambda *args, **kwargs: (
    voice_invocations.append(True) or {{"staged": True, "error": "voice mismatch"}}
)
projection.voice = SimpleNamespace(actions=[1], phone_assignments=[1])

def run_continuity(*states):
    del voice_invocations[:]
    bridge = ContinuityBridge(*states)
    stage_evidence = None
    message = ""
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
            transport=SimpleNamespace(send_and_wait=bridge),
            fingerprint=None,
            packet_tracer_version="9.0.1.0858",
            verified_serial_topology=SimpleNamespace(),
            verified_serial_manifest=SimpleNamespace(),
        )
    except CanonicalLiveFailure as exc:
        stage_evidence = exc.stage_evidence or {{}}
        message = str(exc)
    stage_evidence = stage_evidence or {{}}
    return {{
        "continuity": stage_evidence.get("voice_realtime_continuity"),
        "voice_invoked": bool(voice_invocations),
        "has_voice": "voice" in stage_evidence,
        "has_bindings": "dhcp_server_bindings" in stage_evidence,
        "has_diagnostic": "post_failure_simulation" in stage_evidence,
        "message": message,
        "mode_scripts": sum(
            1 for script in bridge.scripts if "setSimulationMode" in script
        ),
        "state_reads": sum(
            1 for script in bridge.scripts if "isSimulationMode" in script
        ),
    }}

verdict["continuity_verified"] = run_continuity(REALTIME_STATE, REALTIME_STATE)
verdict["continuity_before_simulating"] = run_continuity(SIMULATING_STATE)
verdict["continuity_before_blind"] = run_continuity(None)
verdict["continuity_after_simulating"] = run_continuity(
    REALTIME_STATE, SIMULATING_STATE,
)
verdict["continuity_after_blind"] = run_continuity(REALTIME_STATE, None)

gate_bridge = SimBridge(mode=False)
verdict["diagnostic_gate"] = _post_failure_simulation_diagnostic(
    SimpleNamespace(send_and_wait=gate_bridge), sim_topology(), sim_voice(),
    realtime_failure_established=False,
)
verdict["diagnostic_gate_scripts"] = len(gate_bridge.scripts)

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


def test_voice_dhcp_statistics_are_scoped_and_classify_the_exchange_delta(verdict):
    assert verdict["dhcp_statistics_target"] == {
        "device_name": "Router4",
        "interface": "FastEthernet0/0.20",
        "segment_id": "large-voice",
        "control_interface": "FastEthernet0/0.10",
        "control_segment_id": "large-data",
    }
    # Both scopes, at both points. The voice subinterface alone cannot say
    # whether this build answered for the interface or for the server.
    assert verdict["dhcp_statistics_calls"] == [
        ["Router4", "show_ip_dhcp_server_statistics_interface", "FastEthernet0/0.20"],
        ["Router4", "show_ip_dhcp_server_statistics_interface", "FastEthernet0/0.10"],
        ["Router4", "show_ip_dhcp_server_statistics_interface", "FastEthernet0/0.20"],
        ["Router4", "show_ip_dhcp_server_statistics_interface", "FastEthernet0/0.10"],
    ]
    delta = verdict["dhcp_statistics_delta"]
    assert delta["delta_readable"] is True
    assert delta["scope_discriminated"] is True
    assert delta["counters"] == {
        "discover_received": 21,
        "offer_sent": 21,
        "request_received": 0,
        "ack_sent": 0,
        "nak_sent": 0,
    }
    assert delta["control_counters"] == {
        "discover_received": 23,
        "offer_sent": 23,
        "request_received": 23,
        "ack_sent": 23,
        "nak_sent": 0,
    }
    assert delta["fork"] == "C_OFFER_WITHOUT_REQUEST"


def test_a_voice_scope_indistinguishable_from_the_server_is_not_attributable(verdict):
    """PT support for the scoped form is UNKNOWN, so it has to be observed."""
    unproven = verdict["dhcp_statistics_scope_unproven"]
    assert unproven["scope_discriminated"] is False
    assert unproven["delta_readable"] is False
    assert unproven["counters"] is None
    assert unproven["fork"] == "SCOPE_UNPROVEN"
    assert "did not scope this read" in unproven["failure_reason"]

    # Identical AND silent is a different fact: no table, scoped or global,
    # could have read zero across a window that carried the data clients.
    quiet = verdict["dhcp_statistics_quiet_window"]
    assert quiet["scope_discriminated"] is True
    assert quiet["delta_readable"] is True
    assert quiet["counters"] == {
        "discover_received": 0,
        "offer_sent": 0,
        "request_received": 0,
        "ack_sent": 0,
        "nak_sent": 0,
    }
    assert quiet["fork"] == "A_NO_DISCOVER"

    unreadable = verdict["dhcp_statistics_control_unreadable"]
    assert unreadable["delta_readable"] is False
    assert unreadable["fork"] == "UNOBSERVABLE"
    assert "control scope" in unreadable["failure_reason"]


def test_voice_dhcp_statistics_fail_closed_when_support_or_evidence_is_unclear(verdict):
    unsupported = verdict["dhcp_statistics_unsupported"]
    assert unsupported["usable"] is False
    assert "Invalid input" in unsupported["ios_rejection"]

    truncated = verdict["dhcp_statistics_truncated"]
    assert truncated["usable"] is False
    assert truncated["truncated_by_pager"] is True
    assert truncated["output_complete"] is False

    wrong_identity = verdict["dhcp_statistics_wrong_identity"]
    assert wrong_identity["usable"] is False
    assert wrong_identity["device_identity_confirmed"] is False

    # A counter that went down did not observe negative DHCP traffic; the two
    # captures simply stopped being two points of one series.
    reset = verdict["dhcp_statistics_counter_reset"]
    assert reset["delta_readable"] is False
    assert reset["counters"] is None
    assert reset["fork"] == "UNOBSERVABLE"
    assert "reset or wrapped" in reset["failure_reason"]

    # And without a second pool-backed subinterface on the same server there is
    # nothing to discriminate against, so no target is produced at all.
    assert verdict["dhcp_statistics_target_without_control"] is None


def test_voice_failure_keeps_the_statistics_delta_observation(verdict):
    assert verdict["statistics_before_voice_failure"] == {
        "sentinel": "statistics delta retained",
    }


def test_this_suite_never_loaded_the_production_namespace():
    """The isolation invariant this file must not be the one to break."""
    assert "packet_tracer_mcp" not in sys.modules


def test_the_post_failure_diagnostic_owns_and_returns_the_simulation_mode(verdict):
    """Reversible is not the same as reverted: the window has an owner."""
    realtime = verdict["sim_realtime"]

    assert realtime["diagnostic"] == "POST_FAILURE_SIMULATION_DIAGNOSTIC"
    # The name and the prose must both refuse to be read as the original window.
    assert "NOT the original" in realtime["observes"]
    assert realtime["original_state"]["simulation_mode"] is False
    assert realtime["original_state"]["observed"] is True
    assert realtime["captured"] is True
    assert realtime["restoration_verified"] is True
    assert realtime["restoration"]["changed"] is True
    assert verdict["sim_realtime_final_mode"] is False

    # An operator who was already in Simulation is left exactly there, and the
    # mode is never set when it does not need to change.
    preexisting = verdict["sim_preexisting"]
    assert preexisting["original_state"]["simulation_mode"] is True
    assert preexisting["restoration"]["changed"] is False
    assert preexisting["restoration_verified"] is True
    assert verdict["sim_preexisting_final_mode"] is True
    assert verdict["sim_preexisting_set_calls"] == 0


def test_the_diagnostic_restores_the_mode_on_every_terminal_path(verdict):
    for key in ("sim_trace_timeout", "sim_step_failure"):
        evidence = verdict[key]
        assert evidence["restoration_verified"] is True, key
        assert evidence["captured"] is False, key
        assert verdict[key + "_final_mode"] is False, key

    # A restoration that cannot be verified is recorded on its OWN key and never
    # rewritten as a success.
    stuck = verdict["sim_restore_failed"]
    assert stuck["restoration_verified"] is False
    assert stuck["restoration"]["error"]
    # ...and it does not overwrite what the diagnostic itself observed.
    assert stuck["captured"] is True
    assert stuck["failure_reason"] == ""


def test_the_representative_phone_prerequisites_are_rechecked_this_run(verdict):
    ok = verdict["sim_prereq_ok"]
    assert ok["prerequisites_met"] is True
    assert ok["registration"]["endpoint_interface"] == "Vlan20"
    assert ok["attachment"]["peer_name"] == "Switch5"
    assert ok["attachment"]["endpoint_port"] == "Switch"

    # Each prerequisite is load-bearing, and failing one produces no trace at
    # all rather than a quiet substitution of some other phone.
    for key in (
        "sim_prereq_addressed", "sim_prereq_dhcp_off",
        "sim_prereq_unreadable", "sim_prereq_missing_row",
    ):
        evidence = verdict[key]
        assert evidence["captured"] is False, key
        assert evidence["phone"]["prerequisites_met"] is False, key
        assert evidence["failure_reason"], key
        assert "phone_trace" not in evidence, key
        assert evidence["phone"]["device_name"] == (
            "LARGE-BRANCH-CAMPUS-FLOOR-1-ZONE-A-PHONE-02"
        ), key


def test_an_unattributable_original_state_never_moves_the_mode(verdict):
    blind = verdict["sim_blind"]

    assert blind["captured"] is False
    assert blind["original_state"]["observed"] is False
    assert "not attributable" in blind["failure_reason"]
    assert verdict["sim_blind_mutated"] is False


def test_the_capture_retains_raw_evidence_and_classifies_nothing(verdict):
    realtime = verdict["sim_realtime"]
    trace = realtime["phone_trace"]

    assert trace["limit_reached"] is False
    assert trace["effective_limit"] == 200
    # total_in_event_list is GLOBAL and cannot stand in for a filtered count.
    assert trace["total_in_event_list"] == 4096
    assert trace["hops_captured"] == 1

    hop = trace["hops"][0]
    for field in (
        "index", "device", "previous_device", "in_port", "out_port", "source",
        "destination", "traffic_type_raw", "traffic_type", "sim_time",
        "transit_time", "status", "decisions",
    ):
        assert field in hop, field
    # The raw integer survives beside its label, and the label stays unnamed.
    assert hop["traffic_type_raw"] == 77
    assert hop["traffic_type"] == "type77"
    assert hop["sim_time"] == 3.25
    assert len(hop["decisions"]) == 2
    assert hop["decisions"][0]["layer"] == 3

    # This slice discovers a representation; it does not judge one.
    assert realtime["dhcp_trace_identity"] == "UNOBSERVABLE"
    assert realtime["control_dhcp_visibility"] == "UNOBSERVABLE"
    # An empty control is not proof that DHCP is filtered.
    assert realtime["control_trace"]["hops_captured"] == 0
    assert realtime["control_dhcp_visibility"] == "UNOBSERVABLE"

    assert realtime["step"]["steps_requested"] >= 1
    assert realtime["window_before"]["sim_time"] == 2.5
    assert realtime["window_after"]["sim_time"] == 2.5


def test_the_diagnostic_never_mutates_the_control_endpoint(verdict):
    assert verdict["sim_realtime_mutators"] == []


def test_the_runner_carries_no_dhcp_trace_classifier():
    source = (ROOT / "tools" / "cp_scale_canonical_live.py").read_text(encoding="utf-8")
    start = source.index("def _post_failure_simulation_diagnostic")
    body = source[start:source.index("\ndef ", start + 10)]

    for forbidden in ("0.0.0.0", "255.255.255.255", "DHCPDISCOVER", "bootp", "type67"):
        assert forbidden not in body
    assert "setDhcpClientFlag" not in source


def test_voice_failure_keeps_the_post_failure_simulation_diagnostic(verdict):
    assert verdict["simulation_before_voice_failure"] == {
        "sentinel": "post failure simulation retained",
    }


def test_the_authoritative_voice_window_is_proven_realtime_at_both_edges(verdict):
    """Simulation mode would not slow the window down; it would replace it."""
    outcome = verdict["continuity_verified"]
    continuity = outcome["continuity"]

    assert outcome["voice_invoked"] is True
    assert continuity["verified"] is True
    assert continuity["failure_reason"] == ""
    for edge in ("before", "after"):
        assert continuity[edge]["observed"] is True, edge
        assert continuity[edge]["simulation_mode"] is False, edge
        # The whole pure observation is retained, not just its verdict.
        for field in ("frames", "sim_time", "current_index", "message"):
            assert field in continuity[edge], (edge, field)
    # Two edges are exactly what two reads prove.
    assert "boundaries" in continuity["proves"]
    assert outcome["has_voice"] and outcome["has_diagnostic"]


def test_a_simulating_start_never_runs_the_authoritative_acquisition(verdict):
    for key in ("continuity_before_simulating", "continuity_before_blind"):
        outcome = verdict[key]
        continuity = outcome["continuity"]

        # The window is not entered at all: there is nothing to interpret later.
        assert outcome["voice_invoked"] is False, key
        assert outcome["has_voice"] is False, key
        assert continuity["verified"] is False, key
        assert continuity["failure_reason"], key
        assert continuity["after"] is None, key
        # And the mode is NEVER normalized behind the operator's back.
        assert outcome["mode_scripts"] == 0, key
        assert outcome["state_reads"] >= 1, key
        assert "REALTIME" in outcome["message"].upper(), key


def test_a_simulating_finish_leaves_the_voice_result_uninterpreted(verdict):
    for key in ("continuity_after_simulating", "continuity_after_blind"):
        outcome = verdict[key]
        continuity = outcome["continuity"]

        # The acquisition ran, so its evidence is kept...
        assert outcome["voice_invoked"] is True, key
        assert outcome["has_voice"] is True, key
        # ...but nothing downstream may treat it as an authoritative failure.
        assert continuity["verified"] is False, key
        assert continuity["before"]["simulation_mode"] is False, key
        assert continuity["failure_reason"], key
        assert outcome["has_bindings"] is False, key
        assert outcome["has_diagnostic"] is False, key
        assert outcome["mode_scripts"] == 0, key


def test_the_post_failure_diagnostic_refuses_an_unestablished_failure(verdict):
    gate = verdict["diagnostic_gate"]

    assert gate["status"] == "NOT_APPLICABLE"
    assert gate["captured"] is False
    assert "phone_trace" not in gate
    # It never touches Packet Tracer: there is no valid normal failure to
    # diagnose, so there is no window to open.
    assert verdict["diagnostic_gate_scripts"] == 0


def test_the_two_windows_stay_named_apart(verdict):
    normal = verdict["continuity_verified"]["continuity"]
    diagnostic = verdict["sim_realtime"]

    assert normal["window"] == "NORMAL_WINDOW"
    assert normal["mode_required"] == "realtime"
    assert diagnostic["diagnostic"] == "POST_FAILURE_SIMULATION_DIAGNOSTIC"
    assert "NOT the original" in diagnostic["observes"]
