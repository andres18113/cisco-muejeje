"""Test-only CP-LIVE M0 probes and ordered equivalence comparison.

The production runner imports ``packet_tracer_mcp``.  This module deliberately
does not: every probe that imports the runner executes in a child process, and
only JSON crosses back into pytest's ``src.packet_tracer_mcp`` process.

Every child answers with two separate sections, and they are never mixed:

``trace``
    The comparable, ordered behaviour frozen in the expected artifact.  It is
    compared field by field, keeping destinations, authority, multiplicity,
    order and security decisions exactly as observed.

``provenance``
    What this candidate child measured about itself -- interpreter, loaded
    namespaces, whether the package and runner files resolve inside this tree,
    attempted transport dispatches, and the exact runner symbols it replaced.
    It is asserted as real provenance; it is never compared against a frozen
    expectation and never used to normalize the trace.

What the coordination doubles replace, and what stays real:

* Replaced (Level A): import/Git/process preflight, the HTTP transport, the
  capability snapshot store, composition/projection, the physical, E5, E9 and
  Voice runtimes, ``_execute_stage``, ``_checkpoint``, ``_cleanup_owned``,
  evidence/checkpoint persistence and evidence archiving.  The transport double
  raises on both dispatch methods and every attempt is counted, so a passing
  probe cannot have contacted Packet Tracer or written synthetic capability
  evidence into the product store.
* Real: ``run`` itself -- target contract resolution, the stage loop and its
  order, continuity between stages, checkpoint handling, ``_complete_router0_target``
  and its NO_MUTATION_REPLAY reading, archive/cleanup sequencing, the
  ``except``/``finally`` finalization and the returned code.
* Not proven here: the internal semantics of a stage, a productive full
  qualification, or anything that needs a live Packet Tracer.  Level B and the
  application tests own those.

The policy trace (Level C) replaces nothing at all: it calls the real
forwarding, replay-audit and configuration-acceptance rules with synthetic
typed inputs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from tests.test_cp_scale_router0_live_runner import RUN_DOUBLES


ROOT = Path(__file__).resolve().parents[1]
# The source of the superseded reference: the pre-correction runner, kept so the
# historical artifact stays identifiable.
HARDENING_BASE_SHA = "62db3cea84a4bfca1a5bcd3d2389d62864c45946"
HISTORICAL_FIXTURE_VERSION = "cp-live-m0-fixture-v1"
FIXTURE_VERSION = "cp-live-m0-fixture-v2"


_PROVENANCE = r'''
import sys as _sys
from pathlib import Path as _Path

_TREE = _Path(live.__file__).resolve().parents[1]
dispatch_attempts = []
_product_send = Transport.send
_product_send_and_wait = Transport.send_and_wait


def _counted_send(self, *args, **kwargs):
    dispatch_attempts.append("send")
    return _product_send(self, *args, **kwargs)


def _counted_send_and_wait(self, *args, **kwargs):
    dispatch_attempts.append("send_and_wait")
    return _product_send_and_wait(self, *args, **kwargs)


# The double already refuses to dispatch. Counting the attempt turns
# "no live environment was contacted" into something this run measured.
Transport.send = _counted_send
Transport.send_and_wait = _counted_send_and_wait


def _inside_tree(value):
    try:
        _Path(value).resolve().relative_to(_TREE)
    except (TypeError, ValueError):
        return False
    return True


def candidate_provenance():
    """Measured facts about this child; never compared against the expected."""

    import packet_tracer_mcp

    return {
        "interpreter": _sys.executable,
        "loaded_namespaces": sorted(
            name for name in ("packet_tracer_mcp", "src.packet_tracer_mcp")
            if name in _sys.modules
        ),
        "package_file_inside_tree": _inside_tree(packet_tracer_mcp.__file__),
        "runner_file_inside_tree": _inside_tree(live.__file__),
        "governed_root_inside_tree": _inside_tree(live.GOVERNED_ROOT),
        "transport_dispatch_attempts": list(dispatch_attempts),
        "substituted_runner_symbols": sorted(
            name for name, value in vars(live).items()
            if name in PRODUCT_SYMBOLS and PRODUCT_SYMBOLS[name] is not value
        ),
    }
'''


_CAPTURE_EVIDENCE = r'''
evidence_writes = []


def capture_evidence(evidence):
    snapshot = json.loads(json.dumps(evidence, default=str))
    evidence_writes.append(snapshot)
    active = evidence.get("active_stage")
    record(
        "evidence.write",
        active_stage=(active.get("stage", "") if isinstance(active, dict) else ""),
        failure=bool(evidence.get("failure")),
        closure=str(evidence.get("closure") or ""),
    )


live._write_evidence = capture_evidence


def m0_result(code=None, raised=""):
    """Return only the comparable trace: exit code, ordered events, final."""

    final = evidence_writes[-1] if evidence_writes else {}
    stages = []
    for item in final.get("stages", []):
        if not isinstance(item, dict):
            continue
        stages.append({
            "stage": str(item.get("stage") or ""),
            "stage_outcome": str(item.get("stage_outcome") or ""),
            "verified": item.get("verified"),
            "first_failed_boundary": str(item.get("first_failed_boundary") or ""),
        })
    return {
        "exit_code": code,
        "raised": raised,
        "events": calls,
        "final": {
            "target_stage": str(final.get("target_stage") or ""),
            "closure": str(final.get("closure") or ""),
            "presentation_retained": bool(final.get("presentation_retained")),
            "failure": str(final.get("failure") or ""),
            "stages": stages,
            "no_mutation_replay": final.get("no_mutation_replay"),
            "cleanup": final.get("cleanup"),
            "cleanup_realtime": final.get("cleanup_realtime"),
            "precleanup_archive_error": str(
                final.get("precleanup_archive_error") or ""
            ),
            "cleanup_archive_error": str(final.get("cleanup_archive_error") or ""),
        },
    }


def m0_verdict(code=None, raised=""):
    """Return the comparable trace and this candidate's measured provenance."""

    return {
        "trace": m0_result(code, raised),
        "provenance": candidate_provenance(),
    }
'''


_FULL_ROUTE_OVERRIDES = r'''
live.compose_cp_scale_canonical = lambda **kwargs: SimpleNamespace(
    valid=True,
    issues=[],
    topology=SimpleNamespace(
        devices=[SimpleNamespace(id="full/device")],
        links=[SimpleNamespace(id="full/link")],
    ),
    configuration=object(),
    control_plane=object(),
    capabilities={},
    voice=None,
)
live.reconcile_canonical_stage_deployment = lambda topology, physical, **kwargs: (
    record("reconcile", deployment_id=kwargs.get("deployment_id")) or Deployment()
)
live._full_qualification_projection = lambda composition: projection_for(
    composition, CPScaleCanonicalStage.REMAINING,
)
live._write_checkpoint_summary = lambda stage, evidence, **kwargs: record(
    "summary", stage=stage,
)
'''


_SCENARIO_SOURCES = {
    "router0-cleanup": RUN_DOUBLES + _PROVENANCE + _CAPTURE_EVIDENCE + r'''
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
    target_stage="router0-branch",
)
print(json.dumps(m0_verdict(code)))
''',
    "full-cleanup": (
        RUN_DOUBLES
        + _PROVENANCE
        + _CAPTURE_EVIDENCE
        + _FULL_ROUTE_OVERRIDES
        + r'''
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
)
print(json.dumps(m0_verdict(code)))
'''
    ),
    "full-retain": (
        RUN_DOUBLES
        + _PROVENANCE
        + _CAPTURE_EVIDENCE
        + _FULL_ROUTE_OVERRIDES
        + r'''
def disposition_checkpoint(stage, evidence, *, session_source_head):
    record("checkpoint", stage=stage)
    return "retain" if stage == "full-qualification" else "continue"


live._checkpoint = disposition_checkpoint
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=True,
)
print(json.dumps(m0_verdict(code)))
'''
    ),
    "admission-rejected": RUN_DOUBLES + _PROVENANCE + _CAPTURE_EVIDENCE + r'''
live.compose_cp_scale_canonical = lambda **kwargs: SimpleNamespace(
    valid=False,
    issues=["synthetic admission rejection"],
    topology=SimpleNamespace(devices=[], links=[]),
    configuration=None,
    control_plane=None,
    capabilities={},
)
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
    target_stage="router0-branch",
)
print(json.dumps(m0_verdict(code)))
''',
    "floor2-failure": RUN_DOUBLES + _PROVENANCE + _CAPTURE_EVIDENCE + r'''
successful_execute_stage = live._execute_stage


def fail_floor2(projection, **kwargs):
    if projection.stage is CPScaleCanonicalStage.FLOOR2:
        record(
            "execute_stage",
            stage=projection.stage.value,
            site_forwarding_checks=[],
        )
        raise live.CanonicalLiveFailure(
            "SYNTHETIC_FLOOR2_FAILURE",
            stage_evidence={
                "stage": projection.stage.value,
                "first_failed_boundary": "configuration",
                "stage_outcome": "in_progress",
            },
        )
    return successful_execute_stage(projection, **kwargs)


live._execute_stage = fail_floor2
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
    target_stage="router0-branch",
)
print(json.dumps(m0_verdict(code)))
''',
    "operator-abort": RUN_DOUBLES + _PROVENANCE + _CAPTURE_EVIDENCE + r'''
continued = live._checkpoint


def abort_at_floor1(stage, evidence, *, session_source_head):
    if stage == "floor1":
        record("checkpoint", stage=stage)
        raise live.CanonicalLiveFailure("SYNTHETIC_OPERATOR_ABORT")
    return continued(stage, evidence, session_source_head=session_source_head)


live._checkpoint = abort_at_floor1
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
    target_stage="router0-branch",
)
print(json.dumps(m0_verdict(code)))
''',
    "precleanup-archive-failure": RUN_DOUBLES + _PROVENANCE + _CAPTURE_EVIDENCE + r'''
def fail_precleanup_archive(payload, *, base_dir, run_identity, phase):
    record("archive", phase=phase)
    if phase in {"precleanup", "failure-precleanup"}:
        raise OSError("SYNTHETIC_PRECLEANUP_ARCHIVE_FAILURE")
    return SimpleNamespace(model_dump=lambda mode="json": {"phase": phase})


live.archive_cp_scale_canonical_evidence = fail_precleanup_archive
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
    target_stage="router0-branch",
)
print(json.dumps(m0_verdict(code)))
''',
    "cleanup-failure": RUN_DOUBLES + _PROVENANCE + _CAPTURE_EVIDENCE + r'''
def fail_cleanup(*args, **kwargs):
    record("cleanup")
    raise RuntimeError("SYNTHETIC_CLEANUP_FAILURE")


live._cleanup_owned = fail_cleanup
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
    target_stage="router0-branch",
)
print(json.dumps(m0_verdict(code)))
''',
    "restoration-observation-failure": RUN_DOUBLES + _PROVENANCE + _CAPTURE_EVIDENCE + r'''
live._voice_window_state = lambda runtime: (_ for _ in ()).throw(
    RuntimeError("SYNTHETIC_REALTIME_OBSERVATION_FAILURE")
)
code = live.run(
    "9.0.1.0858",
    expected_head=HEAD,
    retain_on_full_verification=False,
    target_stage="router0-branch",
)
print(json.dumps(m0_verdict(code)))
''',
}


POLICY_TRACE_SOURCE = r'''
import json
import sys as _sys
from pathlib import Path as _Path
from types import SimpleNamespace

import tools.cp_scale_canonical_live as live
import packet_tracer_mcp
from packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleForwardingAuthority,
    CPScaleSiteForwardingCheck,
)
from packet_tracer_mcp.application.use_cases.execute_enterprise_reference import (
    configuration_application_contradiction,
)
from packet_tracer_mcp.application.use_cases.qualify_cp_scale_live import (
    CanonicalMutationSurfaceObservation,
    canonical_stage_configuration_error,
    canonical_stage_mutation_replay_audit,
)
from packet_tracer_mcp.domain.enterprise.models.configuration import (
    ConfigurationPhase,
    ConfigurationPlan,
    ConfigureDhcpPool,
    ConfigureHostname,
    VerificationExpectation,
    VerificationKind,
)
from packet_tracer_mcp.domain.enterprise.models.configuration_runtime import (
    ActionApplicationResult,
    ActionExecutionStatus,
    ConfigurationApplicationResult,
    ConfigurationApplicationStatus,
    FieldVerificationStatus,
    VerificationResult,
)
from packet_tracer_mcp.domain.enterprise.models.execution import MutationDisposition
from packet_tracer_mcp.infrastructure.execution.typed_ping import TypedPingResult

# Level C substitutes nothing: this trace calls the real rules with synthetic
# typed inputs, so the set below stays empty and the probe proves it.
PRODUCT_SYMBOLS = dict(vars(live))
_TREE = _Path(live.__file__).resolve().parents[1]


def _inside_tree(value):
    try:
        _Path(value).resolve().relative_to(_TREE)
    except (TypeError, ValueError):
        return False
    return True


checks = (
    CPScaleSiteForwardingCheck(
        id="forward/large-to-multilayer",
        direction="large-branch-to-multilayer-branch",
        authority=CPScaleForwardingAuthority.DECLARED_TRAFFIC_FLOW,
        declared_traffic_flow_id="flow/large-to-multilayer",
        reverse_of_traffic_flow_id="",
        source_site_id="large-branch",
        destination_site_id="multilayer-branch",
        source_device_id="router-large",
        source_device_name="Router4",
        destination_device_id="endpoint-multilayer",
        destination_device_name="MLS-AP",
        destination_router_id="router-multilayer",
        destination_action_id="cfg/static-multilayer",
        destination_segment_id="segment-multilayer",
        destination_ipv4="192.0.2.20",
        source_topology_hash="e4-hash",
        source_configuration_hash="e5-hash",
    ),
    CPScaleSiteForwardingCheck(
        id="forward/multilayer-to-large",
        direction="multilayer-branch-to-large-branch",
        authority=CPScaleForwardingAuthority.REVERSE_PATH_OF_DECLARED_FLOW,
        declared_traffic_flow_id="",
        reverse_of_traffic_flow_id="flow/large-to-multilayer",
        source_site_id="multilayer-branch",
        destination_site_id="large-branch",
        source_device_id="router-multilayer",
        source_device_name="Router0",
        destination_device_id="endpoint-large",
        destination_device_name="LARGE-AP",
        destination_router_id="router-large",
        destination_action_id="cfg/static-large",
        destination_segment_id="segment-large",
        destination_ipv4="192.0.2.10",
        source_topology_hash="e4-hash",
        source_configuration_hash="e5-hash",
    ),
)


class Ping:
    def __init__(self):
        self.calls = []

    def ping(self, source, destination):
        self.calls.append((source, destination))
        return TypedPingResult(
            reachable=True,
            fresh_output_observed=True,
            dispatched_destination=destination,
            observed_device_name=source,
            device_identity_provenance="confirmed_unique",
            device_identity_evidence="terminal_object_identity",
        )


ping = Ping()
forwarding_verified, forwarding_evidence, first_failure = (
    live._wait_for_site_forwarding(
        ping, checks, attempts=1, interval_seconds=0,
    )
)
operations = []
for sequence, (check, call, evidence) in enumerate(
    zip(checks, ping.calls, forwarding_evidence), start=1,
):
    operations.append({
        "sequence": sequence,
        "phase": "site-forwarding",
        "operation_id": check.id,
        "recipient": call[0],
        "destination": call[1],
        "authority": check.authority.value,
        "declared_traffic_flow_id": check.declared_traffic_flow_id,
        "reverse_of_traffic_flow_id": check.reverse_of_traffic_flow_id,
        "status": "VERIFIED" if evidence["verified"] else "FAILED",
    })


def attempt(*ids):
    return SimpleNamespace(
        mutation_action_ids=ids,
        execution_journal=SimpleNamespace(
            entries=tuple(SimpleNamespace(action_id=item) for item in ids),
        ),
    )


audit = canonical_stage_mutation_replay_audit(
    "router0-branch",
    (
        CanonicalMutationSurfaceObservation(
            surface="configuration",
            plan_action_ids=("cfg/retained", "cfg/new"),
            authorized_mutation_ids=("cfg/new",),
            results=(attempt("cfg/new"), attempt()),
        ),
        CanonicalMutationSurfaceObservation(
            surface="control-plane",
            plan_action_ids=("control/retained", "control/new"),
            authorized_mutation_ids=("control/new",),
            results=(attempt("control/new"),),
        ),
        CanonicalMutationSurfaceObservation(
            surface="voice",
            plan_action_ids=("voice/retained", "voice/new"),
            authorized_mutation_ids=("voice/new",),
            results=(attempt("voice/new"),),
        ),
    ),
)
# A coherent Configuration plan and its read-back. The DHCP pool is the one
# governed observability ceiling this stage claims, so the truthful aggregate
# is PARTIAL: accepted by the canonical rule and still not VERIFIED.
configuration_plan = ConfigurationPlan(
    id="config/cp-live-m0-policy",
    source_topology_id="topology/cp-live-m0-policy",
    source_topology_hash="e4-hash",
    semantic_hash="e5-hash",
    actions=[
        ConfigureHostname(
            id="cfg/hostname-router0",
            phase=ConfigurationPhase.IDENTITY,
            device_id="router-multilayer",
            device_name="Router0",
            site_id="multilayer-branch",
            hostname="Router0",
        ),
        ConfigureDhcpPool(
            id="cfg/dhcp-multilayer",
            phase=ConfigurationPhase.SERVICES,
            device_id="router-multilayer",
            device_name="Router0",
            site_id="multilayer-branch",
            pool_name="MULTILAYER",
            segment_id="segment-multilayer",
            network="192.0.2.0",
            prefix=24,
            netmask="255.255.255.0",
            gateway="192.0.2.1",
            lease_start="192.0.2.10",
            lease_end="192.0.2.60",
        ),
    ],
    verification_expectations=[
        VerificationExpectation(
            id="verify/hostname-router0",
            action_id="cfg/hostname-router0",
            kind=VerificationKind.HOSTNAME,
            device_id="router-multilayer",
            device_name="Router0",
            expected={"hostname": "Router0"},
        ),
        VerificationExpectation(
            id="verify/dhcp-multilayer",
            action_id="cfg/dhcp-multilayer",
            kind=VerificationKind.DHCP_POOL,
            device_id="router-multilayer",
            device_name="Router0",
            expected={"pool_name": "MULTILAYER", "network": "192.0.2.0"},
        ),
    ],
)
configuration_result = ConfigurationApplicationResult(
    config_plan_id=configuration_plan.id,
    config_semantic_hash=configuration_plan.semantic_hash,
    source_topology_hash=configuration_plan.source_topology_hash,
    status=ConfigurationApplicationStatus.PARTIAL,
    action_results=[
        ActionApplicationResult(
            action_id=item.id,
            status=ActionExecutionStatus.APPLIED,
            disposition=MutationDisposition.CHANGED,
        )
        for item in configuration_plan.actions
    ],
    mutation_action_ids=[item.id for item in configuration_plan.actions],
    verification_results=[
        VerificationResult(
            expectation_id="verify/hostname-router0",
            action_id="cfg/hostname-router0",
            status=ActionExecutionStatus.VERIFIED,
            evidence_method="fresh_typed_readback",
            fresh_evidence=True,
            fields={"hostname": FieldVerificationStatus.VERIFIED},
        ),
        VerificationResult(
            expectation_id="verify/dhcp-multilayer",
            action_id="cfg/dhcp-multilayer",
            status=ActionExecutionStatus.UNOBSERVABLE,
            evidence_method="runtime_observability_limit",
            fresh_evidence=False,
            fields={
                "pool_name": FieldVerificationStatus.UNOBSERVABLE,
                "network": FieldVerificationStatus.UNOBSERVABLE,
            },
        ),
    ],
)

# The rejection: the same run claiming it read the pool back. Nothing in it
# contradicts the plan, which is exactly why an absent contradiction may never
# stand in for canonical acceptance.
promoted_ceiling = configuration_result.model_copy(deep=True)
promoted_ceiling.status = ConfigurationApplicationStatus.VERIFIED
promoted_ceiling.verification_results[1].status = ActionExecutionStatus.VERIFIED
promoted_ceiling.verification_results[1].evidence_method = "fresh_typed_readback"
promoted_ceiling.verification_results[1].fresh_evidence = True
promoted_ceiling.verification_results[1].fields = {
    "pool_name": FieldVerificationStatus.VERIFIED,
    "network": FieldVerificationStatus.VERIFIED,
}


def configuration_decision(candidate):
    acceptance_error = canonical_stage_configuration_error(
        configuration_plan, candidate,
    )
    contradiction = configuration_application_contradiction(candidate)
    return {
        "config_plan_id": candidate.config_plan_id,
        "aggregate_status": candidate.status.value,
        "canonical_acceptance_error": acceptance_error,
        "canonically_accepted": acceptance_error == "",
        "contradiction": contradiction,
        "contradiction_free": contradiction == "",
        "fully_verified": (
            candidate.status is ConfigurationApplicationStatus.VERIFIED
            and acceptance_error == ""
        ),
    }


print(json.dumps({
    "trace": {
        "operations": operations,
        "forwarding": {
            "verified": forwarding_verified,
            "first_failure": first_failure,
        },
        "replay": audit.compact_summary(),
        "configuration": {
            "accepted_with_governed_ceiling": configuration_decision(
                configuration_result,
            ),
            "rejected_promoted_ceiling": configuration_decision(promoted_ceiling),
        },
    },
    "provenance": {
        "interpreter": _sys.executable,
        "loaded_namespaces": sorted(
            name for name in ("packet_tracer_mcp", "src.packet_tracer_mcp")
            if name in _sys.modules
        ),
        "package_file_inside_tree": _inside_tree(packet_tracer_mcp.__file__),
        "runner_file_inside_tree": _inside_tree(live.__file__),
        "governed_root_inside_tree": _inside_tree(live.GOVERNED_ROOT),
        "transport_dispatch_attempts": [],
        "substituted_runner_symbols": sorted(
            name for name, value in vars(live).items()
            if name in PRODUCT_SYMBOLS and PRODUCT_SYMBOLS[name] is not value
        ),
    },
}))
'''


SCENARIOS = tuple(sorted(_SCENARIO_SOURCES))


def coordination_source(scenario: str) -> str:
    """Return a closed set of reviewed child sources; never interpolate input."""

    try:
        return _SCENARIO_SOURCES[scenario]
    except KeyError as exc:
        raise ValueError(f"Unknown CP-LIVE M0 scenario: {scenario}") from exc


def run_product_probe(source: str, isolated_dir: Path) -> dict[str, Any]:
    """Run production-namespace code with no product transport or host state."""

    isolated_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    # A custom PYTHONPATH would invalidate the governed namespace baseline.
    environment.pop("PYTHONPATH", None)
    environment.update({
        "LOCALAPPDATA": str(isolated_dir),
        "TEMP": str(isolated_dir),
        "TMP": str(isolated_dir),
        "PT_MCP_BRIDGE_TOKEN": "cp-live-m0-synthetic-token",
        "PT_MCP_GOVERNED_ROOT": str(ROOT),
    })
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr or completed.stdout
    lines = completed.stdout.strip().splitlines()
    assert lines, "CP-LIVE M0 child produced no JSON verdict"
    return json.loads(lines[-1])


def trace_differences(
    expected: Any,
    actual: Any,
    *,
    path: str = "$",
) -> list[str]:
    """Return exact ordered differences without hiding duplicates or authority."""

    if type(expected) is not type(actual):
        return [
            f"{path}: type {type(expected).__name__} != {type(actual).__name__}"
        ]
    if isinstance(expected, dict):
        differences: list[str] = []
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys):
            differences.append(f"{path}.{key}: missing")
        for key in sorted(actual_keys - expected_keys):
            differences.append(f"{path}.{key}: unexpected")
        for key in expected:
            if key in actual:
                differences.extend(trace_differences(
                    expected[key], actual[key], path=f"{path}.{key}",
                ))
        return differences
    if isinstance(expected, list):
        differences = []
        if len(expected) != len(actual):
            differences.append(
                f"{path}: length {len(expected)} != {len(actual)}"
            )
        for index, (expected_item, actual_item) in enumerate(
            zip(expected, actual),
        ):
            differences.extend(trace_differences(
                expected_item, actual_item, path=f"{path}[{index}]",
            ))
        return differences
    if expected != actual:
        return [f"{path}: {expected!r} != {actual!r}"]
    return []
