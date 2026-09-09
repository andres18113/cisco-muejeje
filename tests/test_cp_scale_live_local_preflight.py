"""The extracted local preflight with controlled, read-only environment readers."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.packet_tracer_mcp.application.cp_scale_live import (
    CPScaleCheckState,
    CPScaleImportIsolationObservation,
    CPScaleLiveRequest,
    CPScaleLocalPreflight,
    CPScalePreflightOutcome,
    CPScaleProcessObservation,
    CPScaleProcessRecord,
    CPScaleRepositoryObservation,
    CPScaleRuntimeEvidence,
    process_record_mapping,
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
    return CPScaleLiveRequest(**values)


def _inspect(service, request=None):
    return service.inspect(
        request or _request(),
        run_identity="run-id",
        started_at=STARTED,
    )


def test_success_uses_the_real_coordinator_and_process_policy_with_controlled_readers():
    events = []
    result = _inspect(_service(events=events))

    assert events == ["runtime", "imports", "repository", "processes"]
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

    assert events == ["runtime", "imports", "repository", "processes"]
    assert result.outcome is CPScalePreflightOutcome.REJECTED
    assert result.issues == ("No running Packet Tracer process was observed.",)
    assert result.process.state is CPScaleCheckState.FAILED
    assert result.process.processes == ()


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
