"""The extracted local preflight with controlled, read-only environment readers."""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.application.cp_scale_live import (
    CPScaleCheckState,
    CPScaleCallObservabilityEvidence,
    CPScaleImportIsolationObservation,
    CPScaleLiveAuthorizationRequest,
    CPScaleLiveRequest,
    CPScaleLocalPreflight,
    CPScalePreflightOutcome,
    CPScaleProcessObservation,
    CPScaleProcessRecord,
    CPScaleRepositoryObservation,
    CPScaleRuntimeEvidence,
    process_record_mapping,
)
from src.packet_tracer_mcp.application.use_cases.compose_cp_scale_canonical import (
    CPScaleCanonicalTarget,
    canonical_cp_scale_target_contract,
)
from src.packet_tracer_mcp.domain.enterprise.models.voice_runtime import (
    PhoneExecutionMethod,
)
from src.packet_tracer_mcp.infrastructure.execution.cp_scale_live_preflight import (
    GitCPScaleRepositoryReader,
    PacketTracerImportIsolationReader,
    PowerShellPacketTracerProcessReader,
    PythonRuntimeEvidenceReader,
)
from src.packet_tracer_mcp.infrastructure.execution.live_environment_preflight import (
    packet_tracer_process_error,
)


ROOT = Path("C:/governed")
HEAD = "a" * 40
TREE = "b" * 40
STARTED = datetime(2026, 9, 8, 12, 30, tzinfo=timezone.utc)
PROCESS = CPScaleProcessRecord(
    pid=101,
    name="PacketTracer",
    main_window_handle=0,
    product_version="9.0.1.0858",
    file_version="9.0.1.0858",
    executable_path=(
        r"C:\Program Files\Cisco Packet Tracer\bin\PacketTracer.exe"
    ),
)


class Reader:
    def __init__(self, name, value, events):
        self.name = name
        self.value = value
        self.events = events

    def read(self, *args):
        self.events.append(self.name)
        return self.value


def _service(
    *,
    runtime=None,
    imports=None,
    repository=None,
    processes=None,
    call_observability=None,
    events=None,
):
    calls = events if events is not None else []
    return CPScaleLocalPreflight(
        governed_root=ROOT,
        runtime_reader=Reader(
            "runtime",
            runtime or CPScaleRuntimeEvidence(
                python_executable="C:/governed/.venv/Scripts/python.exe",
                package_file="C:/governed/src/packet_tracer_mcp/__init__.py",
                loaded_namespaces=("packet_tracer_mcp",),
            ),
            calls,
        ),
        import_reader=Reader(
            "imports",
            imports or CPScaleImportIsolationObservation(
                isolated=True,
                isolation_state="ISOLATED",
                detail="C:/governed/src/packet_tracer_mcp/__init__.py",
            ),
            calls,
        ),
        repository_reader=Reader(
            "repository",
            repository or CPScaleRepositoryObservation(
                branch="feature/runtime-ripv2",
                upstream="cisco/feature/runtime-ripv2",
                head=HEAD,
                upstream_head=HEAD,
                source_tree=TREE,
                dirty=False,
            ),
            calls,
        ),
        call_observability_reader=Reader(
            "call_observability",
            call_observability or CPScaleCallObservabilityEvidence(
                state=CPScaleCheckState.PASSED,
                required=True,
                expectation_results=("established", "not_connected"),
                provider_id="packet-tracer-native-ui-mailbox-v1",
                execution_method=PhoneExecutionMethod.PACKET_TRACER_NATIVE_UI,
                packet_tracer_version="9.0.1.0858",
                call_control_models=("2811",),
                phone_models=("7960",),
                qualification_run_identity="call-observability-qualification/run-1",
                qualification_executed_sha="c" * 40,
                evidence_path="docs/reference/cp-scale/call-observability.json",
                evidence_sha256="d" * 64,
                driver_source_sha256="e" * 64,
            ),
            calls,
        ),
        process_reader=Reader(
            "processes",
            processes or CPScaleProcessObservation(processes=(PROCESS,)),
            calls,
        ),
        process_error_policy=packet_tracer_process_error,
        expected_branch="feature/runtime-ripv2",
        expected_upstream="cisco/feature/runtime-ripv2",
    )


def _request(**changes):
    values = {
        "packet_tracer_version": "9.0.1.0858",
        "expected_head": HEAD,
        "retain_on_full_verification": False,
        "target_stage": "full-qualification",
    }
    values.update(changes)
    # Every canonical target needs its own explicit authorization; a test that
    # studies its absence says so with ``live_authorization=None``.
    values.setdefault(
        "live_authorization",
        _authorization(target=values["target_stage"]),
    )
    return CPScaleLiveRequest(**values)


def _authorization(
    *,
    target: str = "full-qualification",
    authorized_sha: str = HEAD,
) -> CPScaleLiveAuthorizationRequest:
    return CPScaleLiveAuthorizationRequest(
        target=target,
        authorized_sha=authorized_sha,
    )


def _inspect(service, request=None):
    return service.inspect(
        request or _request(),
        run_identity="run-id",
        started_at=STARTED,
    )


def test_success_uses_the_real_coordinator_and_process_policy_with_controlled_readers():
    events = []
    result = _inspect(_service(events=events))

    assert events == [
        "runtime", "imports", "repository", "call_observability", "processes",
    ]
    assert result.outcome is CPScalePreflightOutcome.ADMITTED
    assert result.issues == ()
    assert result.evidence_coherent is True
    assert result.identity is not None
    assert result.identity.source_head == HEAD
    assert result.identity.source_tree == TREE
    assert result.identity.python_executable.endswith("python.exe")
    assert result.identity.loaded_namespace == "packet_tracer_mcp"
    assert not hasattr(result.identity, "environment_fingerprint")
    assert process_record_mapping(result.process.processes[0]) == {
        "ProcessName": "PacketTracer",
        "Id": 101,
        "MainWindowHandle": 0,
        "ProductVersion": "9.0.1.0858",
        "FileVersion": "9.0.1.0858",
        "Path": r"C:\Program Files\Cisco Packet Tracer\bin\PacketTracer.exe",
    }


def test_request_rejection_marks_every_check_not_run_and_reads_no_boundary():
    events = []
    result = _inspect(_service(events=events), _request(
        retain_on_full_verification=True,
        target_stage="router0-branch",
    ))

    assert events == ["runtime"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == (
        "Router0 target cannot be combined with full-scale retention.",
    )
    assert result.import_isolation.state is CPScaleCheckState.NOT_RUN
    assert result.repository.state is CPScaleCheckState.NOT_RUN
    assert result.process.state is CPScaleCheckState.NOT_RUN


TARGETS = ("router0-branch", "router3-branch", "full-qualification")


@pytest.mark.parametrize("target", TARGETS)
def test_every_live_target_without_authorization_is_rejected_before_pt(target):
    events = []
    result = _inspect(
        _service(events=events),
        _request(target_stage=target, live_authorization=None),
    )

    assert events == ["runtime"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == (
        f"LIVE target {target!r} requires an explicit target- and "
        "SHA-scoped authorization.",
    )
    assert result.import_isolation.state is CPScaleCheckState.NOT_RUN
    assert result.repository.state is CPScaleCheckState.NOT_RUN
    assert result.process.state is CPScaleCheckState.NOT_RUN


@pytest.mark.parametrize(
    ("request_changes", "expected_issue"),
    [
        # Each target once as the authorized one and once as the requested one.
        *(
            pytest.param(
                {
                    "target_stage": requested,
                    "live_authorization": _authorization(target=authorized),
                },
                (
                    f"LIVE authorization for {authorized!r} does not "
                    f"authorize requested target {requested!r}."
                ),
                id=f"{authorized}-for-{requested}",
            )
            for authorized, requested in zip(TARGETS, TARGETS[1:] + TARGETS[:1])
        ),
        pytest.param(
            {"live_authorization": _authorization(authorized_sha="c" * 40)},
            (
                f"LIVE authorized SHA {'c' * 40!r} does not match "
                f"request expected HEAD {HEAD!r}."
            ),
            id="authorized-sha-does-not-match-request",
        ),
        pytest.param(
            {"live_authorization": _authorization(authorized_sha=HEAD.upper())},
            "LIVE authorized SHA must be exactly 40 lowercase hexadecimal characters.",
            id="authorized-sha-not-canonical",
        ),
        pytest.param(
            {"live_authorization": _authorization(target="remaining")},
            "LIVE authorization target is invalid; observed 'remaining'.",
            id="stage-is-not-a-live-target",
        ),
    ],
)
def test_authorization_is_target_and_sha_scoped_before_pt(
    request_changes,
    expected_issue,
):
    events = []
    result = _inspect(
        _service(events=events),
        _request(**request_changes),
    )

    assert events == ["runtime"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == (expected_issue,)
    assert result.repository.state is CPScaleCheckState.NOT_RUN
    assert result.process.state is CPScaleCheckState.NOT_RUN


@pytest.mark.parametrize(
    ("target", "target_name"),
    [("router3-branch", "Router3"), ("full-qualification", "Full")],
)
def test_retention_is_rejected_before_pt_with_valid_authorization(target, target_name):
    events = []
    result = _inspect(
        _service(events=events),
        _request(target_stage=target, retain_on_full_verification=True),
    )

    assert events == ["runtime"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == (
        f"{target_name} target cannot be combined with full-scale retention.",
    )
    assert result.process.state is CPScaleCheckState.NOT_RUN


def test_authorization_preserves_existing_repository_head_gate():
    authorized_sha = "c" * 40
    events = []
    result = _inspect(
        _service(events=events),
        _request(
            expected_head=authorized_sha,
            live_authorization=_authorization(authorized_sha=authorized_sha),
        ),
    )

    assert events == ["runtime", "imports", "repository"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == (
        f"Expected HEAD {authorized_sha!r}; observed {HEAD!r}.",
    )
    assert result.process.state is CPScaleCheckState.NOT_RUN
    assert result.live_authorization is not None
    assert result.live_authorization.repository_head == HEAD
    assert result.live_authorization.upstream_head == HEAD
    assert result.live_authorization.source_tree == TREE


@pytest.mark.parametrize("target", TARGETS)
def test_authorization_binds_exact_repository_provenance(target):
    events = []
    result = _inspect(_service(events=events), _request(target_stage=target))

    expected = ["runtime", "imports", "repository"]
    if target == "full-qualification":
        expected.append("call_observability")
    expected.append("processes")
    assert events == expected
    assert result.outcome is CPScalePreflightOutcome.ADMITTED
    authorization = result.live_authorization
    assert authorization is not None
    assert authorization.authorized_target.value == target
    assert authorization.authorized_sha == HEAD
    assert authorization.expected_head == HEAD
    assert authorization.repository_head == HEAD
    assert authorization.upstream_head == HEAD
    assert authorization.source_tree == TREE
    assert authorization.passed_coherently is True
    assert result.evidence_coherent is True


@pytest.mark.parametrize(
    "changes",
    [
        pytest.param({"authorized_sha": "c" * 40}, id="authorized-sha"),
        pytest.param({"expected_head": "c" * 40}, id="expected-head"),
        pytest.param({"repository_head": "c" * 40}, id="repository-head"),
        pytest.param({"upstream_head": "c" * 40}, id="upstream-head"),
        pytest.param({"source_tree": "d" * 40}, id="source-tree"),
        pytest.param(
            dict.fromkeys(
                (
                    "authorized_sha",
                    "expected_head",
                    "repository_head",
                    "upstream_head",
                ),
                "c" * 40,
            ),
            id="self-consistent-foreign-head",
        ),
        pytest.param(
            {"authorized_target": CPScaleCanonicalTarget.ROUTER3_BRANCH},
            id="another-target",
        ),
    ],
)
def test_authorization_cannot_contradict_observed_provenance(changes):
    admitted = _inspect(_service(), _request())
    assert admitted.outcome is CPScalePreflightOutcome.ADMITTED
    assert all(
        re.fullmatch(r"[0-9a-f]{40}", value)
        for key, value in changes.items() if key != "authorized_target"
    )

    candidate = replace(
        admitted,
        live_authorization=replace(admitted.live_authorization, **changes),
    )

    assert candidate.issues == ()
    assert candidate.evidence_coherent is False
    assert candidate.outcome is CPScalePreflightOutcome.REJECTED


def test_authorization_provenance_is_persisted_without_secrets():
    from src.packet_tracer_mcp.application.cp_scale_live.run_contracts import (
        CPScaleRunReport,
    )
    from src.packet_tracer_mcp.infrastructure.persistence.cp_scale_run_evidence import (
        run_evidence,
    )

    preflight = _inspect(_service(), _request())
    payload = run_evidence(CPScaleRunReport(
        preflight=preflight,
        run_identity="run-id",
        started_at=STARTED,
        packet_tracer_version="9.0.1.0858",
    ))

    assert payload["live_authorization"] == {
        "authorized_target": "full-qualification",
        "authorized_sha": HEAD,
        "expected_head": HEAD,
        "repository_head": HEAD,
        "upstream_head": HEAD,
        "source_tree": TREE,
    }
    assert payload["call_observability"] == {
        "state": "passed",
        "required": True,
        "expectation_results": ["established", "not_connected"],
        "provider_id": "packet-tracer-native-ui-mailbox-v1",
        "execution_method": "packet_tracer_native_ui",
        "packet_tracer_version": "9.0.1.0858",
        "call_control_models": ["2811"],
        "phone_models": ["7960"],
        "qualification_run_identity": "call-observability-qualification/run-1",
        "qualification_executed_sha": "c" * 40,
        "evidence_path": "docs/reference/cp-scale/call-observability.json",
        "evidence_sha256": "d" * 64,
        "driver_source_sha256": "e" * 64,
        "error": "",
    }


def test_import_rejection_short_circuits_before_repository_and_processes():
    events = []
    result = _inspect(_service(
        events=events,
        imports=CPScaleImportIsolationObservation(
            isolated=False,
            isolation_state="DUAL_IDENTITY",
            detail="packet_tracer_mcp + src.packet_tracer_mcp",
            error="DUAL_IDENTITY: rejected",
        ),
    ))

    assert events == ["runtime", "imports"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == ("DUAL_IDENTITY: rejected",)
    assert result.import_isolation.state is CPScaleCheckState.FAILED
    assert result.repository.state is CPScaleCheckState.NOT_RUN
    assert result.process.state is CPScaleCheckState.NOT_RUN


def test_repository_rejection_preserves_order_duplicates_and_skips_processes():
    events = []
    result = _inspect(_service(
        events=events,
        repository=CPScaleRepositoryObservation(
            branch="feature/runtime-ripv2",
            upstream="cisco/feature/runtime-ripv2",
            head=HEAD,
            upstream_head=HEAD,
            source_tree=TREE,
            dirty=None,
            error="same repository issue",
            dirty_error="same repository issue",
        ),
    ))

    assert events == ["runtime", "imports", "repository"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == (
        "same repository issue",
        "same repository issue",
    )
    assert result.repository.state is CPScaleCheckState.FAILED
    assert result.process.state is CPScaleCheckState.NOT_RUN


def test_process_rejection_is_the_last_local_boundary_and_retains_empty_evidence():
    events = []
    result = _inspect(_service(
        events=events,
        processes=CPScaleProcessObservation(),
    ))

    assert events == [
        "runtime", "imports", "repository", "call_observability", "processes",
    ]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == ("No running Packet Tracer process was observed.",)
    assert result.process.state is CPScaleCheckState.FAILED
    assert result.process.processes == ()


def test_full_without_qualified_phone_control_rejects_before_process_or_pt():
    events = []
    result = _inspect(_service(
        events=events,
        call_observability=CPScaleCallObservabilityEvidence(
            state=CPScaleCheckState.FAILED,
            required=True,
            packet_tracer_version="9.0.1.0858",
            error="No qualified observable PhoneControl provider is available.",
        ),
    ))

    assert events == ["runtime", "imports", "repository", "call_observability"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == (
        "No qualified observable PhoneControl provider is available.",
    )
    assert result.call_observability.state is CPScaleCheckState.FAILED
    assert result.process.state is CPScaleCheckState.NOT_RUN


@pytest.mark.parametrize(
    ("change", "value"),
    (
        ("packet_tracer_version", "9.0.2.0000"),
        ("provider_id", "foreign-provider"),
        ("call_control_models", ("1941",)),
        ("phone_models", ("7970",)),
        ("qualification_executed_sha", "not-a-sha"),
        ("evidence_sha256", "not-a-hash"),
        ("driver_source_sha256", "not-a-hash"),
    ),
)
def test_full_rejects_stale_or_foreign_call_qualification(change, value):
    qualified = _service()._call_observability_reader.value
    candidate = replace(qualified, **{change: value})

    result = _inspect(_service(call_observability=candidate))

    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.process.state is CPScaleCheckState.NOT_RUN
    assert "call observability" in result.issues[0].casefold()


@pytest.mark.parametrize("target", ("router0-branch", "router3-branch"))
def test_bounded_router_targets_do_not_acquire_or_require_call_provider(target):
    events = []
    result = _inspect(_service(
        events=events,
        call_observability=CPScaleCallObservabilityEvidence(
            state=CPScaleCheckState.FAILED,
            error="must not be read",
        ),
    ), _request(target_stage=target))

    assert result.outcome is CPScalePreflightOutcome.ADMITTED
    assert "call_observability" not in events
    assert result.call_observability.state is CPScaleCheckState.NOT_RUN


def test_only_full_target_declares_call_observability_readiness():
    assert canonical_cp_scale_target_contract(
        "full-qualification"
    ).requires_call_observability is True
    assert canonical_cp_scale_target_contract(
        "router0-branch"
    ).requires_call_observability is False
    assert canonical_cp_scale_target_contract(
        "router3-branch"
    ).requires_call_observability is False


@pytest.mark.parametrize(
    "boundary",
    ["import", "repository", "process", "process-absent", "identity"],
)
def test_no_check_state_or_missing_evidence_can_continue(boundary):
    admitted = _inspect(_service())
    if boundary == "import":
        candidate = replace(
            admitted,
            import_isolation=replace(
                admitted.import_isolation,
                state=CPScaleCheckState.NOT_RUN,
            ),
        )
    elif boundary == "repository":
        candidate = replace(
            admitted,
            repository=replace(
                admitted.repository,
                state=CPScaleCheckState.FAILED,
            ),
        )
    elif boundary == "process":
        candidate = replace(
            admitted,
            process=replace(
                admitted.process,
                state=CPScaleCheckState.NOT_RUN,
            ),
        )
    elif boundary == "process-absent":
        candidate = replace(admitted, process=None)
    else:
        candidate = replace(admitted, identity=None)

    assert candidate.issues == ()
    assert candidate.outcome is CPScalePreflightOutcome.REJECTED


def test_incoherent_passed_evidence_and_nonempty_issues_both_block():
    admitted = _inspect(_service())
    dirty = replace(
        admitted,
        repository=replace(admitted.repository, dirty=True),
    )
    wrong_version = replace(
        admitted,
        process=replace(
            admitted.process,
            processes=(replace(PROCESS, product_version="8.2.0"),),
        ),
    )
    issue = replace(admitted, issues=("late issue",))

    assert dirty.repository.state is CPScaleCheckState.PASSED
    assert dirty.outcome is CPScalePreflightOutcome.REJECTED
    assert wrong_version.process.state is CPScaleCheckState.PASSED
    assert wrong_version.outcome is CPScalePreflightOutcome.REJECTED
    assert issue.outcome is CPScalePreflightOutcome.REJECTED


def test_process_reader_preserves_path_and_both_version_fields():
    payload = {
        "ProcessName": "PacketTracer",
        "Id": 77,
        "MainWindowHandle": 0,
        "ProductVersion": "9.0.1.0858-product",
        "FileVersion": "9.0.1.0858-file",
        "Path": r"C:\PT\PacketTracer.exe",
    }
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout=json.dumps(payload))

    result = PowerShellPacketTracerProcessReader(run_command=run).read()

    assert result.error == ""
    assert result.processes == (
        CPScaleProcessRecord(
            pid=77,
            name="PacketTracer",
            main_window_handle=0,
            product_version="9.0.1.0858-product",
            file_version="9.0.1.0858-file",
            executable_path=r"C:\PT\PacketTracer.exe",
        ),
    )
    assert calls[0][0][:3] == ["powershell.exe", "-NoProfile", "-Command"]
    assert calls[0][1] == {
        "check": True,
        "capture_output": True,
        "text": True,
    }


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("ProcessName", 7),
        ("ProductVersion", ["9.0.1.0858"]),
        ("FileVersion", {"value": "9.0.1.0858"}),
        ("Path", [r"C:\PT\PacketTracer.exe"]),
    ],
)
def test_process_reader_rejects_invalid_text_types_instead_of_stringifying(
    field,
    invalid,
):
    payload = {
        "ProcessName": "PacketTracer",
        "Id": 77,
        "MainWindowHandle": 0,
        "ProductVersion": "9.0.1.0858",
        "FileVersion": "9.0.1.0858",
        "Path": r"C:\PT\PacketTracer.exe",
    }
    payload[field] = invalid

    result = PowerShellPacketTracerProcessReader(
        run_command=lambda *_args, **_kwargs: SimpleNamespace(
            stdout=json.dumps(payload),
        ),
    ).read()

    assert result.processes == ()
    assert f"{field} must be a string" in result.error


def test_process_reader_preserves_file_version_fallback_when_product_is_absent():
    payload = {
        "ProcessName": "PacketTracer",
        "Id": 77,
        "MainWindowHandle": 0,
        "ProductVersion": None,
        "FileVersion": "9.0.1.0858-file",
        "Path": r"C:\PT\PacketTracer.exe",
    }
    result = PowerShellPacketTracerProcessReader(
        run_command=lambda *_args, **_kwargs: SimpleNamespace(
            stdout=json.dumps(payload),
        ),
    ).read()

    assert result.error == ""
    assert result.processes[0].product_version == ""
    assert result.processes[0].file_version == "9.0.1.0858-file"
    assert packet_tracer_process_error(
        [process_record_mapping(result.processes[0])],
        "9.0.1.0858",
    ) == ""


def test_git_reader_pins_the_tree_to_the_captured_head_and_rechecks_references():
    calls = []
    values = {
        ("branch", "--show-current"): "feature/runtime-ripv2",
        ("rev-parse", "--abbrev-ref", "@{upstream}"): (
            "cisco/feature/runtime-ripv2"
        ),
        ("rev-parse", "HEAD"): HEAD,
        ("status", "--porcelain"): "",
        ("rev-parse", "@{upstream}"): HEAD,
        ("rev-parse", f"{HEAD}^{{tree}}"): TREE,
    }

    def git(root, *arguments):
        calls.append((root, arguments))
        return values[arguments]

    result = GitCPScaleRepositoryReader(git_output=git).read(ROOT)

    assert [arguments for _, arguments in calls] == [
        ("branch", "--show-current"),
        ("rev-parse", "--abbrev-ref", "@{upstream}"),
        ("rev-parse", "HEAD"),
        ("status", "--porcelain"),
        ("rev-parse", "@{upstream}"),
        ("rev-parse", f"{HEAD}^{{tree}}"),
        ("rev-parse", "HEAD"),
        ("rev-parse", "@{upstream}"),
    ]
    assert all(root == ROOT for root, _ in calls)
    assert result == CPScaleRepositoryObservation(
        branch="feature/runtime-ripv2",
        upstream="cisco/feature/runtime-ripv2",
        head=HEAD,
        upstream_head=HEAD,
        source_tree=TREE,
        dirty=False,
    )


@pytest.mark.parametrize("moving_reference", ["head", "upstream"])
def test_git_reader_rejects_a_reference_that_moves_during_its_snapshot(
    moving_reference,
):
    moved = "c" * 40
    head_values = iter((HEAD, moved if moving_reference == "head" else HEAD))
    upstream_values = iter(
        (HEAD, moved if moving_reference == "upstream" else HEAD),
    )

    def git(_root, *arguments):
        if arguments == ("branch", "--show-current"):
            return "feature/runtime-ripv2"
        if arguments == ("rev-parse", "--abbrev-ref", "@{upstream}"):
            return "cisco/feature/runtime-ripv2"
        if arguments == ("rev-parse", "HEAD"):
            return next(head_values)
        if arguments == ("status", "--porcelain"):
            return ""
        if arguments == ("rev-parse", "@{upstream}"):
            return next(upstream_values)
        if arguments == ("rev-parse", f"{HEAD}^{{tree}}"):
            return TREE
        raise AssertionError(arguments)

    result = GitCPScaleRepositoryReader(git_output=git).read(ROOT)

    assert result.source_tree == TREE
    if moving_reference == "head":
        assert "HEAD changed during repository inspection" in result.source_tree_error
        assert result.upstream_head_error == ""
    else:
        assert "upstream changed during repository inspection" in (
            result.upstream_head_error
        )
        assert result.source_tree_error == ""


def test_repository_snapshot_error_short_circuits_before_process_inspection():
    events = []
    result = _inspect(_service(
        events=events,
        repository=CPScaleRepositoryObservation(
            branch="feature/runtime-ripv2",
            upstream="cisco/feature/runtime-ripv2",
            head=HEAD,
            upstream_head=HEAD,
            source_tree=TREE,
            dirty=False,
            source_tree_error="HEAD changed during repository inspection.",
        ),
    ))

    assert events == ["runtime", "imports", "repository"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == ("HEAD changed during repository inspection.",)
    assert result.process.state is CPScaleCheckState.NOT_RUN


def test_runtime_reader_observes_loaded_modules_without_importing_anything():
    production = SimpleNamespace(__file__="C:/tree/src/packet_tracer_mcp/__init__.py")
    modules = {
        "packet_tracer_mcp": production,
        "src.packet_tracer_mcp": object(),
    }

    result = PythonRuntimeEvidenceReader(
        executable=lambda: "C:/tree/.venv/Scripts/python.exe",
        modules=lambda: modules,
    ).read()

    assert result == CPScaleRuntimeEvidence(
        python_executable="C:/tree/.venv/Scripts/python.exe",
        package_file="C:/tree/src/packet_tracer_mcp/__init__.py",
        loaded_namespaces=("packet_tracer_mcp", "src.packet_tracer_mcp"),
    )


def test_import_reader_reuses_the_existing_isolation_result_and_rendering():
    result = SimpleNamespace(
        isolated=False,
        state=SimpleNamespace(value="FOREIGN_TREE"),
        detail="C:/foreign/package.py",
        render=lambda: "FOREIGN_TREE: rejected",
    )
    reader = PacketTracerImportIsolationReader(
        factory=lambda root: SimpleNamespace(ensure_isolated=lambda: result),
    )

    observed = reader.read(ROOT)

    assert observed == CPScaleImportIsolationObservation(
        isolated=False,
        isolation_state="FOREIGN_TREE",
        detail="C:/foreign/package.py",
        error="FOREIGN_TREE: rejected",
    )
