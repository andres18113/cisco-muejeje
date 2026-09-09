"""Isolated behavioral tests for the production-namespace LIVE runner."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _probe(source: str) -> dict:
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_runner_dispatches_both_typed_branch_directions_and_fails_each_closed():
    verdict = _probe(r'''
import json

import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleForwardingAuthority,
    CPScaleSiteForwardingCheck,
)
from packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingResult

checks = tuple(
    CPScaleSiteForwardingCheck(
        id=f"check-{index}",
        direction=direction,
        authority=authority,
        declared_traffic_flow_id=(
            "flow/large-to-multilayer"
            if authority is CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW
            else ""
        ),
        reverse_of_traffic_flow_id=(
            ""
            if authority is CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW
            else "flow/large-to-multilayer"
        ),
        source_site_id=source_site,
        destination_site_id=destination_site,
        source_device_id=source_id,
        source_device_name=source_name,
        destination_device_id=destination_id,
        destination_device_name=destination_name,
        destination_router_id=destination_router_id,
        destination_action_id=f"cfg/static-{index}",
        destination_segment_id=f"segment-{index}",
        destination_ipv4=destination_ipv4,
        source_topology_hash="e4-hash",
        source_configuration_hash="e5-hash",
    )
    for index, (
        direction, authority, source_site, destination_site, source_id,
        source_name, destination_id, destination_name, destination_router_id,
        destination_ipv4,
    ) in enumerate((
        (
            "large-branch-to-multilayer-branch",
            CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW,
            "large-branch", "multilayer-branch", "router-large", "Router4",
            "endpoint-multilayer", "MLS-AP", "router-multilayer", "192.0.2.20",
        ),
        (
            "multilayer-branch-to-large-branch",
            CPScaleForwardingAuthority.REVERSE_PATH_OF_DECLARED_FLOW,
            "multilayer-branch", "large-branch", "router-multilayer", "Router0",
            "endpoint-large", "LARGE-AP", "router-large", "192.0.2.10",
        ),
    ))
)

class Ping:
    def __init__(self, failed=None, stale=False):
        self.failed = failed
        self.stale = stale
        self.calls = []

    def ping(self, source, destination):
        self.calls.append((source, destination))
        index = len(self.calls) - 1
        return TypedPingResult(
            reachable=index != self.failed,
            fresh_output_observed=not self.stale,
            dispatched_destination=destination,
            observed_device_name=source,
            device_identity_provenance="confirmed_unique",
            device_identity_evidence="terminal_object_identity",
        )

success_ping = Ping()
success, evidence, first = live._wait_for_site_forwarding(
    success_ping, checks, attempts=1, interval_seconds=0,
)
failures = []
for failed in (0, 1):
    ping = Ping(failed=failed)
    verified, failed_evidence, first_failure = live._wait_for_site_forwarding(
        ping, checks, attempts=1, interval_seconds=0,
    )
    failures.append({
        "verified": verified,
        "first": first_failure,
        "evidence": failed_evidence,
    })
stale, _, stale_first = live._wait_for_site_forwarding(
    Ping(stale=True), checks, attempts=1, interval_seconds=0,
)
print(json.dumps({
    "success": success,
    "first": first,
    "calls": success_ping.calls,
    "evidence": evidence,
    "failures": failures,
    "stale": stale,
    "stale_first": stale_first,
}))
''')

    assert verdict["success"] is True
    assert verdict["first"] == ""
    assert verdict["calls"] == [
        ["Router4", "192.0.2.20"],
        ["Router0", "192.0.2.10"],
    ]
    assert all(item["verified"] for item in verdict["evidence"])
    assert [item["first"] for item in verdict["failures"]] == [
        "check-0", "check-1",
    ]
    assert not any(item["verified"] for item in verdict["failures"])
    assert verdict["stale"] is False
    assert verdict["stale_first"] == "check-0"


def test_runner_router0_terminal_sequence_is_successful_and_stops_at_target():
    verdict = _probe(r'''
import json
import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)

contract = canonical_cp_scale_target_contract(CPScaleCanonicalTarget.ROUTER0_BRANCH)
events = []
live._write_evidence = lambda evidence: events.append("write")
live._write_checkpoint_summary = lambda stage, evidence: events.append(
    "summary:" + stage
)
live._cleanup_owned = lambda *args, **kwargs: (
    events.append("cleanup")
    or {"verified": True, "first": {}, "second": {}, "restoration_error": ""}
)

def observe_realtime():
    events.append("realtime")
    return {"verified": True, "error": ""}

def archive(phase, payload):
    events.append("archive:" + phase)
    return {"phase": phase, "path": phase + ".json"}

def audited(stage):
    return {
        "stage": stage,
        "verified": True,
        "site_forwarding_verified": True,
        "plan": {"branch_forwarding_checks": [{"id": "forward-1"}]},
        "site_forwarding": [{"check": {"id": "forward-1"}, "verified": True}],
        "workspace_verified_twice": True,
        "mutation_replay_audit": {
            "stage": stage,
            "claim": "NO_MUTATION_REPLAY",
            "verified": True,
            "surfaces": [{
                "surface": "configuration",
                "verified": True,
                "replayed_retained_ids": [],
            }],
        },
    }

evidence = {
    "stages": [audited("floor3"), audited("router0-branch")],
    "live_devices": 290,
    "live_links": 202,
}
result = live._complete_router0_target(
    evidence=evidence,
    target_contract=contract,
    physical=object(),
    full_topology=object(),
    owned_device_ids=set(),
    baseline=object(),
    observe_cleanup_realtime=observe_realtime,
    archive=archive,
    run_identity="run-id",
    session_source_head="a" * 40,
)
print(json.dumps({
    "events": events,
    "closure": evidence["closure"],
    "scope": evidence["closure_scope"],
    "no_mutation_replay": evidence["no_mutation_replay"],
    "attested": result["cleanup_attestation"],
    "result": result,
    "build_stages": [item.value for item in contract.build_stages],
    "remaining": contract.run_remaining_reconciliation,
    "full": contract.run_full_qualification,
}))
''')

    assert verdict["events"] == [
        "write",
        "archive:precleanup",
        "cleanup",
        "realtime",
        "archive:cleanup",
        "write",
        "summary:router0-branch",
    ]
    assert verdict["closure"] == "ROUTER0_BRANCH_VERIFIED_AND_CLEANED"
    assert verdict["scope"] == "router0-branch"
    assert verdict["no_mutation_replay"] == {
        "claim": "NO_MUTATION_REPLAY",
        "verified": True,
        "audited_stages": ["floor3", "router0-branch"],
        "stages_without_verified_audit": [],
        "replayed_retained_ids": [],
    }
    assert verdict["build_stages"][-1] == "router0-branch"
    assert "router3-branch" not in verdict["build_stages"]
    assert verdict["remaining"] is False
    assert verdict["full"] is False


@pytest.mark.parametrize(
    ("failure", "expected_events"),
    [
        ("precleanup", ["write", "archive:precleanup"]),
        (
            "first-restoration",
            ["write", "archive:precleanup", "cleanup", "realtime"],
        ),
        (
            "second-restoration",
            ["write", "archive:precleanup", "cleanup", "realtime"],
        ),
        (
            "realtime",
            ["write", "archive:precleanup", "cleanup", "realtime"],
        ),
        (
            "cleanup-archive",
            [
                "write", "archive:precleanup", "cleanup", "realtime",
                "archive:cleanup",
            ],
        ),
    ],
)
def test_runner_never_publishes_router0_success_before_every_terminal_gate(
    failure,
    expected_events,
):
    verdict = _probe(rf'''
import json
import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)

failure = {failure!r}
contract = canonical_cp_scale_target_contract(CPScaleCanonicalTarget.ROUTER0_BRANCH)
events = []
live._write_evidence = lambda evidence: events.append("write")
live._write_checkpoint_summary = lambda stage, evidence: events.append("summary")

def cleanup(*args, **kwargs):
    events.append("cleanup")
    restoration = failure if "restoration" in failure else ""
    return {{
        "verified": not restoration,
        "restoration_error": restoration,
        "first": {{}},
        "second": {{}},
    }}

live._cleanup_owned = cleanup

def realtime():
    events.append("realtime")
    return {{
        "verified": failure != "realtime",
        "error": "realtime" if failure == "realtime" else "",
    }}

def archive(phase, payload):
    events.append("archive:" + phase)
    if failure == phase or (failure == "cleanup-archive" and phase == "cleanup"):
        raise RuntimeError("archive failed: " + phase)
    return {{"phase": phase}}

evidence = {{
    "stages": [{{
        "stage": "router0-branch",
        "verified": True,
        "site_forwarding_verified": True,
        "plan": {{"branch_forwarding_checks": [{{"id": "forward-1"}}]}},
        "site_forwarding": [{{
            "check": {{"id": "forward-1"}}, "verified": True,
        }}],
        "workspace_verified_twice": True,
        "mutation_replay_audit": {{
            "stage": "router0-branch",
            "claim": "NO_MUTATION_REPLAY",
            "verified": True,
            "surfaces": [],
        }},
    }}],
}}
try:
    live._complete_router0_target(
        evidence=evidence,
        target_contract=contract,
        physical=object(),
        full_topology=object(),
        owned_device_ids=set(),
        baseline=object(),
        observe_cleanup_realtime=realtime,
        archive=archive,
        run_identity="run-id",
        session_source_head="a" * 40,
    )
    error = ""
except Exception as exc:
    error = type(exc).__name__ + ": " + str(exc)
print(json.dumps({{
    "events": events,
    "error": error,
    "closure": evidence.get("closure", ""),
}}))
''')

    assert verdict["events"] == expected_events
    assert verdict["error"]
    assert verdict["closure"] != "ROUTER0_BRANCH_VERIFIED_AND_CLEANED"


def test_api_rejects_invalid_or_retained_router0_target_before_pt_contact():
    verdict = _probe(r'''
import inspect
import json
from types import SimpleNamespace
import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)

contacted = False
def contact():
    global contacted
    contacted = True
    raise AssertionError("Packet Tracer contact was attempted")

live.PacketTracerImportIsolationReader = lambda: SimpleNamespace(read=contact)
live.GitCPScaleRepositoryReader = lambda: SimpleNamespace(read=contact)
live.PowerShellPacketTracerProcessReader = lambda: SimpleNamespace(read=contact)
live._write_evidence = lambda evidence: None
try:
    live.run(
        "9.0.1.0858",
        expected_head="a" * 40,
        retain_on_full_verification=False,
        target_stage="unknown",
    )
    invalid = ""
except ValueError as exc:
    invalid = str(exc)

retained = live.run(
    "9.0.1.0858",
    expected_head="a" * 40,
    retain_on_full_verification=True,
    target_stage="router0-branch",
)
default_target = inspect.signature(live.run).parameters["target_stage"].default
full_contract = canonical_cp_scale_target_contract(default_target)
print(json.dumps({
    "invalid": invalid,
    "retained": retained,
    "contacted": contacted,
    "default_target": default_target.value,
    "default_stages": [item.value for item in full_contract.build_stages],
    "legacy_stages": [item.value for item in live._BUILD_STAGES],
    "remaining": full_contract.run_remaining_reconciliation,
    "full": full_contract.run_full_qualification,
}))
''')

    assert verdict["invalid"]
    assert verdict["retained"] == 2
    assert verdict["contacted"] is False
    assert verdict["default_target"] == "full-qualification"
    assert verdict["default_stages"] == verdict["legacy_stages"]
    assert verdict["remaining"] is True
    assert verdict["full"] is True


@pytest.mark.parametrize(
    ("audit", "expected_replay"),
    [
        pytest.param(
            {
                "stage": "floor2",
                "claim": "MUTATION_REPLAY_DETECTED",
                "verified": False,
                "surfaces": [{
                    "surface": "configuration",
                    "verified": False,
                    "replayed_retained_ids": ["cfg/access/floor1/1"],
                }],
            },
            ["cfg/access/floor1/1"],
            id="retained-action-executed-again",
        ),
        pytest.param(None, [], id="stage-never-audited"),
    ],
)
def test_a_replayed_retained_action_blocks_the_router0_closure(
    audit,
    expected_replay,
):
    verdict = _probe(rf'''
import json
import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)

contract = canonical_cp_scale_target_contract(CPScaleCanonicalTarget.ROUTER0_BRANCH)
events = []
live._write_evidence = lambda evidence: events.append("write")
live._write_checkpoint_summary = lambda stage, evidence: events.append("summary")
live._cleanup_owned = lambda *args, **kwargs: (
    events.append("cleanup") or {{"verified": True}}
)

def realtime():
    events.append("realtime")
    return {{"verified": True, "error": ""}}

def archive(phase, payload):
    events.append("archive:" + phase)
    return {{"phase": phase}}

def stage(name, audit):
    evidence = {{
        "stage": name,
        "verified": True,
        "site_forwarding_verified": True,
        "plan": {{"branch_forwarding_checks": [{{"id": "forward-1"}}]}},
        "site_forwarding": [{{
            "check": {{"id": "forward-1"}}, "verified": True,
        }}],
        "workspace_verified_twice": True,
    }}
    if audit is not None:
        evidence["mutation_replay_audit"] = audit
    return evidence

verified_audit = {{
    "stage": "router0-branch",
    "claim": "NO_MUTATION_REPLAY",
    "verified": True,
    "surfaces": [],
}}
evidence = {{
    "stages": [
        stage("floor2", {audit!r}),
        stage("router0-branch", verified_audit),
    ],
}}
try:
    live._complete_router0_target(
        evidence=evidence,
        target_contract=contract,
        physical=object(),
        full_topology=object(),
        owned_device_ids=set(),
        baseline=object(),
        observe_cleanup_realtime=realtime,
        archive=archive,
        run_identity="run-id",
        session_source_head="a" * 40,
    )
    error = ""
except Exception as exc:
    error = type(exc).__name__ + ": " + str(exc)
print(json.dumps({{
    "events": events,
    "error": error,
    "closure": evidence.get("closure", ""),
    "verdict": evidence.get("no_mutation_replay"),
}}))
''')

    assert verdict["events"] == []
    assert "NO_MUTATION_REPLAY" in verdict["error"]
    assert "floor2" in verdict["error"]
    assert verdict["closure"] == ""
    assert verdict["verdict"] == {
        "claim": "MUTATION_REPLAY_DETECTED",
        "verified": False,
        "audited_stages": ["floor2", "router0-branch"],
        "stages_without_verified_audit": ["floor2"],
        "replayed_retained_ids": expected_replay,
    }


RUN_DOUBLES = r'''
import json
from types import SimpleNamespace

import tools.cp_scale_canonical_live as live
from packet_tracer_mcp.application.cp_scale_live import (
    CPScaleCheckState,
    CPScaleImportIsolationEvidence,
    CPScaleLiveSessionIdentity,
    CPScalePreflightResult,
    CPScaleProcessEvidence,
    CPScaleProcessRecord,
    CPScaleRepositoryEvidence,
    CPScaleRuntimeEvidence,
)
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalStage,
    CPScaleCanonicalStageTransition,
)
from packet_tracer_mcp.domain.enterprise.models.physical_deployment import (
    PhysicalDeploymentStatus,
)

# Taken before the first double is installed, so a probe can name exactly which
# runner symbols it replaced instead of asserting a hand-written list.
PRODUCT_SYMBOLS = dict(vars(live))

HEAD = "a" * 40
calls = []


def record(event, **fields):
    calls.append({"event": event, **fields})


class Transport:
    """Connected, and refuses to dispatch anything: this run never touches PT."""

    bridge_transport = "http"
    is_connected = True

    def start(self, timeout_seconds=0.0):
        record("transport.start")
        return True

    def status_dict(self):
        return {"connected": True}

    def stop(self):
        record("transport.stop")

    def send(self, *args, **kwargs):
        raise AssertionError("A LIVE dispatch was attempted.")

    def send_and_wait(self, *args, **kwargs):
        raise AssertionError("A LIVE dispatch was attempted.")


class Workspace:
    def compact_summary(self):
        return {"devices": 0}


class Physical:
    def __init__(self, *args, **kwargs):
        pass

    def observe_workspace(self):
        return Workspace()


class Deployment:
    status = PhysicalDeploymentStatus.VERIFIED
    manifest = SimpleNamespace(deployment_id="deployment/1")
    errors = ()
    item_results = ()

    def model_dump(self, mode="json"):
        return {"status": "verified"}


class Deployer:
    def __init__(self, physical):
        pass

    def deploy(self, topology, **kwargs):
        record("deploy", deployment_id=kwargs.get("deployment_id"))
        return Deployment()


def projection_for(composition, stage, **kwargs):
    record("project", stage=stage.value)
    return SimpleNamespace(
        stage=stage,
        topology=SimpleNamespace(
            devices=[SimpleNamespace(id=stage.value + "/device")],
            links=[SimpleNamespace(id=stage.value + "/link")],
            modules=[],
            physical_identity_hash="e4/" + stage.value,
        ),
        configuration=SimpleNamespace(
            actions=[], semantic_hash="e5/" + stage.value, verification_expectations=[],
        ),
        control_plane=SimpleNamespace(
            actions=[], semantic_hash="e9/" + stage.value, verification_expectations=[],
        ),
        voice=SimpleNamespace(actions=[], phone_assignments=[]),
        forwarding_checks={},
        branch_forwarding_checks=(
            (ForwardingCheck(id="forward-1"),)
            if stage is CPScaleCanonicalStage.ROUTER0_BRANCH else ()
        ),
    )


def execute_stage(projection, **kwargs):
    stage = projection.stage
    record(
        "execute_stage",
        stage=stage.value,
        site_forwarding_checks=[
            item.id for item in kwargs.get("site_forwarding_checks", ())
        ],
    )
    evidence = {
        "stage": stage.value,
        "verified": True,
        "workspace_verified_twice": True,
        "control_plane": {"action_results": []},
        "voice": {"result": {"action_results": []}},
        "plan": {
            "branch_forwarding_checks": [
                {"id": item.id}
                for item in kwargs.get("site_forwarding_checks", ())
            ],
        },
        "mutation_replay_audit": {
            "stage": stage.value,
            "claim": "NO_MUTATION_REPLAY",
            "verified": True,
            "surfaces": [],
        },
    }
    if stage is CPScaleCanonicalStage.ROUTER0_BRANCH:
        evidence["site_forwarding_verified"] = True
        evidence["site_forwarding"] = [
            {"check": {"id": "forward-1"}, "verified": True},
        ]
    from packet_tracer_mcp.application.cp_scale_live.contracts import (
        CPScaleLiveStageResult, CPScaleStageContinuity, CPScaleStageReport,
        CPScaleMutationScope, CPScaleForwardingResult, CPScaleSiteForwardingObservation,
    )
    from packet_tracer_mcp.domain.models.typed_ping import TypedPingResult
    control = SimpleNamespace(action_results=(), model_dump=lambda mode: {"action_results": []})
    forwarding = (
        CPScaleForwardingResult(True, (), tuple(
            CPScaleSiteForwardingObservation(check, (TypedPingResult(True, True),), True)
            for check in kwargs.get("site_forwarding_checks", ())
        ), True) if kwargs.get("site_forwarding_checks") else None
    )
    return CPScaleLiveStageResult(
        stage=stage, outcome="verified", projection=projection, deployment=Deployment(),
        delta_deployment=None, manifest=Deployment().manifest, workspace=Workspace(),
        configuration=object(), configuration_accepted=True, configuration_attempts=(),
        control_plane=control, voice=None,
        replay_audit=SimpleNamespace(compact_summary=lambda: evidence["mutation_replay_audit"]),
        orientation=None, required_observations=(), diagnostics=(), first_failed_boundary=None,
        failure="", continuity=CPScaleStageContinuity(), report=CPScaleStageReport(
            CPScaleMutationScope((), (), (), (), (), ()), None, None, (), None, None, "",
            forwarding, Workspace(), Workspace(), True, tuple(kwargs.get("site_forwarding_checks", ())),
        ),
    )


from dataclasses import dataclass

@dataclass(frozen=True)
class ForwardingCheck:
    id: str


class StageExecutor:
    def execute(self, request):
        return execute_stage(request.projection, site_forwarding_checks=request.site_forwarding_checks)


def transition_contract(previous, current):
    record(
        "transition",
        previous=previous.stage.value,
        current=current.stage.value,
    )
    return CPScaleCanonicalStageTransition(
        previous_stage=previous.stage,
        current_stage=current.stage,
        new_device_ids=("router0-branch/device",),
        anchor_device_ids=(),
        new_link_ids=(),
        configuration_mutation_ids=(),
        configuration_retained_ids=(),
        control_plane_mutation_ids=(),
        control_plane_retained_ids=(),
        voice_mutation_ids=(),
        voice_retained_ids=(),
        replayed_configuration_ids=(),
        replayed_control_plane_ids=(),
        replayed_voice_ids=(),
    )


def checkpoint(stage, evidence, *, session_source_head):
    record("checkpoint", stage=stage)
    return "continue"


def cleanup_owned(physical, topology, owned, baseline):
    record("cleanup")
    return {"verified": True, "restoration_error": ""}


def archive_evidence(payload, *, base_dir, run_identity, phase):
    record("archive", phase=phase)
    return SimpleNamespace(model_dump=lambda mode="json": {"phase": phase})


def reconcile(topology, physical, **kwargs):
    deployment_id = kwargs.get("deployment_id")
    record("reconcile", deployment_id=deployment_id)
    if deployment_id == "cp-scale-canonical/remaining/reconciliation":
        # The boundary this test measures: reached by the default target,
        # never by Router0.
        raise RuntimeError("remaining reconciliation reached")
    return Deployment()


def refuse_full_qualification(composition):
    raise AssertionError("Full qualification must not be projected.")


class LocalPreflight:
    def inspect(self, request, *, run_identity, started_at):
        target = live.canonical_cp_scale_target_contract(request.target_stage)
        runtime = CPScaleRuntimeEvidence(
            python_executable=live.sys.executable,
            package_file=live.packet_tracer_mcp.__file__,
            loaded_namespaces=("packet_tracer_mcp",),
        )
        repository = CPScaleRepositoryEvidence(
            state=CPScaleCheckState.PASSED,
            branch=live.EXPECTED_BRANCH,
            upstream=live.EXPECTED_UPSTREAM,
            head=HEAD,
            upstream_head=HEAD,
            source_tree="b" * 40,
            dirty=False,
        )
        process = CPScaleProcessEvidence(
            state=CPScaleCheckState.PASSED,
            processes=(CPScaleProcessRecord(
                pid=1,
                name="PacketTracer",
                main_window_handle=0,
                product_version=request.packet_tracer_version,
                file_version=request.packet_tracer_version,
                executable_path=r"C:\\PacketTracer.exe",
            ),),
        )
        return CPScalePreflightResult(
            target=target,
            runtime=runtime,
            import_isolation=CPScaleImportIsolationEvidence(
                state=CPScaleCheckState.PASSED,
                isolation_state="ISOLATED",
                detail=runtime.package_file,
            ),
            repository=repository,
            process=process,
            identity=CPScaleLiveSessionIdentity(
                run_identity=run_identity,
                started_at=started_at,
                packet_tracer_version=request.packet_tracer_version,
                source_head=HEAD,
                source_tree=repository.source_tree,
                branch=repository.branch,
                upstream=repository.upstream,
                python_executable=runtime.python_executable,
                package_file=runtime.package_file,
                loaded_namespace="packet_tracer_mcp",
            ),
            issues=(),
        )


live._build_local_preflight = lambda: LocalPreflight()
live.PacketTracerHttpTransport = Transport
live.PacketTracerPhysicalTopologyRuntime = Physical
live.disposable_workspace_error = lambda observation: ""
live.CapabilitySnapshotStore = lambda base_dir: object()
live.compose_cp_scale_canonical = lambda **kwargs: SimpleNamespace(
    valid=True,
    issues=[],
    topology=object(),
    configuration=object(),
    control_plane=object(),
    capabilities={},
)
live.canonical_required_capability_probes = lambda composition: {}
live.PacketTracerBridgeProbeRuntime = lambda *args, **kwargs: object()
live.CapabilityDiscoveryService = lambda **kwargs: object()
live.EnterpriseCapabilityAdapter = lambda: SimpleNamespace(
    identity_for=None, access_ports_for=None,
)
live.canonical_cleanup_restoration_error = lambda *args: ""
live.project_cp_scale_canonical_stage = projection_for
live._voice_dhcp_statistics_target = lambda configuration, voice: None
live.EnterprisePhysicalTopologyDeployer = Deployer
live.ControlledIosExecutor = lambda *args, **kwargs: object()
live.PacketTracerEnterpriseConfigurationRuntime = (
    lambda *args, **kwargs: object()
)
live.PacketTracerEnterpriseControlPlaneRuntime = (
    lambda *args, **kwargs: object()
)
live.PacketTracerEnterpriseVoiceRuntime = lambda *args, **kwargs: object()
live.canonical_delta_deployment_error = lambda *args, **kwargs: ""
live.canonical_stage_resume_error = lambda *args, **kwargs: ""
live._network_state_observation = lambda *args, **kwargs: {}
live.project_cp_scale_canonical_delta = (
    lambda previous, current: SimpleNamespace(
        devices=(), modules=(), links=(),
    )
)
live.canonical_stage_transition_contract = transition_contract
live.reconcile_canonical_stage_deployment = reconcile
live._build_stage_executor = lambda **kwargs: StageExecutor()
live._checkpoint = checkpoint
live._cleanup_owned = cleanup_owned
live._write_evidence = lambda evidence: None
live._write_checkpoint_summary = lambda stage, evidence: record(
    "summary", stage=stage,
)
live.archive_cp_scale_canonical_evidence = archive_evidence
live.SimulationTraceRuntime = lambda *args, **kwargs: object()
live._voice_window_state = lambda runtime: {"mode": "realtime"}
live._realtime_boundary_error = lambda state, edge: ""
live._full_qualification_projection = refuse_full_qualification
'''


def test_run_reaches_router0_cleanup_and_never_enters_the_later_stages():
    verdict = _probe(RUN_DOUBLES + r'''
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
    target_stage="router0-branch",
)
print(json.dumps({"code": code, "calls": calls}))
''')

    assert verdict["code"] == 0
    calls = verdict["calls"]
    build = [
        item["stage"] for item in calls if item["event"] == "execute_stage"
    ]
    assert build == [
        "routing-core",
        "router4-switch10",
        "floor1",
        "floor2",
        "floor3",
        "router0-branch",
    ]
    # Physical manifest assembly happens once before each incremental stage;
    # it is distinct from the two terminal workspace reads tested on the real
    # StageExecutor. Neither gate may be moved or duplicated by extraction.
    assert [item["event"] for item in calls if item["event"] in {
        "deploy", "reconcile", "execute_stage",
    }] == ["deploy", "execute_stage"] + ["deploy", "reconcile", "execute_stage"] * 5
    assert [item["event"] for item in calls[-6:]] == [
        "execute_stage", "archive", "cleanup", "archive", "summary",
        "transport.stop",
    ]
    assert [
        item["phase"] for item in calls if item["event"] == "archive"
    ] == ["precleanup", "cleanup"]

    # Router0 is the only stage given branch forwarding, and the only stage
    # whose boundary is proven by the transition contract.
    assert [
        (item["stage"], item["site_forwarding_checks"])
        for item in calls
        if item["event"] == "execute_stage" and item["site_forwarding_checks"]
    ] == [("router0-branch", ["forward-1"])]
    assert [
        (item["previous"], item["current"])
        for item in calls if item["event"] == "transition"
    ] == [("floor3", "router0-branch")]

    # Nothing after the terminal stage: no checkpoint asking to continue, no
    # Router3, no remaining reconciliation, no full qualification.
    assert [
        item["stage"] for item in calls if item["event"] == "checkpoint"
    ] == ["routing-core", "router4-switch10", "floor1", "floor2", "floor3"]
    projected = {item["stage"] for item in calls if item["event"] == "project"}
    assert "router3-branch" not in projected
    assert "remaining" not in projected
    assert not any(
        "router3-branch" in str(item.get("deployment_id") or "")
        or "remaining" in str(item.get("deployment_id") or "")
        for item in calls if item["event"] in {"deploy", "reconcile"}
    )


def test_default_run_still_walks_past_router0_into_router3():
    verdict = _probe(RUN_DOUBLES + r'''
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
)
print(json.dumps({"code": code, "calls": calls}))
''')

    calls = verdict["calls"]
    build = [
        item["stage"] for item in calls if item["event"] == "execute_stage"
    ]
    # The default target does not stop at Router0: it checkpoints it like any
    # other stage, builds Router3, and reaches the remaining reconciliation
    # this double refuses.
    assert build == [
        "routing-core",
        "router4-switch10",
        "floor1",
        "floor2",
        "floor3",
        "router0-branch",
        "router3-branch",
    ]
    assert "router0-branch" in [
        item["stage"] for item in calls if item["event"] == "checkpoint"
    ]
    assert "remaining" in {
        item["stage"] for item in calls if item["event"] == "project"
    }
    assert "cp-scale-canonical/remaining/reconciliation" in [
        item["deployment_id"] for item in calls if item["event"] == "reconcile"
    ]
    assert verdict["code"] == 1

    # Neither the Router0 boundary contract nor its branch forwarding belongs
    # to the default route.
    assert not any(item["event"] == "transition" for item in calls)
    assert not any(
        item["event"] == "execute_stage" and item["site_forwarding_checks"]
        for item in calls
    )
